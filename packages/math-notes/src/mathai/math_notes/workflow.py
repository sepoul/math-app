"""Math-notes ingest graph — transcribe a voice note + parse the photos.

Two nodes: `TranscribeNoteStep` pulls the uploaded audio off the storage
plane (via the platform's `AudioInterpreter`) and transcribes it; then
`ParsePagesStep` vision-parses each notebook photo (via the platform's
`ImageInterpreter`) into a structured `ParsedPage`. Both thread their
output onto state for `_persist` to mint a `DailyNoteArtifact` (+ a
`NotePageArtifact` per photo).

    TranscribeNoteStep → ParsePagesStep → End

The OpenAI SDK ships in the worker base and the two interpreters are
platform provider helpers, so this domain pulls **no** AI dependency of
its own. The module imports `pydantic_graph` (the light platform graph
framework); the heavy work (HTTP download + model calls) is deferred to
run time and offloaded to threads so it doesn't block the graph's event
loop. Page parsing is best-effort enrichment: it no-ops when no photos
are attached or the vision helper isn't deployed yet.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_notes.artifacts import ParsedPage
from mathai.math_notes.state import MathNotesState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ai_platform.ai.providers.audio import AudioInterpreter
    from ai_platform.ai.providers.vision import ImageInterpreter


@dataclass
class MathNotesWorkflowDependencies:
    """Per-run inputs for the math_notes graph.

    `note_date` arrives as an ISO date string from the JSON submit payload
    (or None); the node resolves it to a `date`, defaulting to today. The
    `interpreter` is the platform's `AudioInterpreter` and `image_interpreter`
    its `ImageInterpreter` (both built once per worker, over a
    `PlatformSession`); `image_interpreter` is `None` until the vision helper
    is deployed, in which case page parsing is skipped. `interpreter` is
    `None` only in degenerate/test paths.
    """

    audio_ref: str = ""
    image_refs: list[str] = field(default_factory=list)
    note_date: Optional[str] = None
    created_by: Optional[str] = None
    interpreter: Optional["AudioInterpreter"] = None
    image_interpreter: Optional["ImageInterpreter"] = None
    logger: WorkerLogger = field(default_factory=NullLogger)


@dataclass
class TranscribeNoteStep(
    BaseNode[MathNotesState, MathNotesWorkflowDependencies, MathNotesState]
):
    """Transcribe the uploaded voice note; record it (+ refs + date) on state."""

    stage_label = "Transcribe note"
    stage_description = (
        "Transcribe the voice note (OpenAI) and record it as a DailyNoteArtifact"
    )

    async def run(
        self, ctx: GraphRunContext[MathNotesState, MathNotesWorkflowDependencies]
    ) -> "ParsePagesStep":
        log = ctx.deps.logger.for_stage("TranscribeNoteStep")
        resolved_date = (
            date.fromisoformat(ctx.deps.note_date) if ctx.deps.note_date else date.today()
        )
        await log.info(
            f"transcribing note for {resolved_date.isoformat()} "
            f"(audio={ctx.deps.audio_ref!r}, images={len(ctx.deps.image_refs)})"
        )

        transcript: Optional[str] = None
        if ctx.deps.interpreter is not None and ctx.deps.audio_ref:
            # Blocking work (HTTP download + OpenAI). Offload to a thread so the
            # graph's event loop isn't blocked.
            result = await asyncio.to_thread(
                ctx.deps.interpreter.transcribe, ctx.deps.audio_ref
            )
            transcript = result.text
            await log.info(f"transcribed {len(transcript)} chars")

        ctx.state.audio_ref = ctx.deps.audio_ref
        ctx.state.image_refs = ctx.deps.image_refs
        ctx.state.transcript = transcript
        ctx.state.note_date = resolved_date
        ctx.state.created_by = ctx.deps.created_by
        return ParsePagesStep()


# Instruction handed to the generic platform `ImageInterpreter`. The helper
# returns plain text; we ask it for JSON and parse it here (domain-side), per
# the §13 boundary — the platform stays unaware of math/LaTeX/concepts.
_PAGE_PROMPT = (
    "You are reading a photo of a page of handwritten mathematics study "
    "notes. Return ONLY a JSON object (no prose, no markdown fences) with "
    "these keys:\n"
    '  "text": a faithful plain-text transcription of the page,\n'
    '  "latex": the mathematical content as LaTeX (empty string if none),\n'
    '  "diagram_description": a short description of any diagram or figure '
    "on the page (empty string if none),\n"
    '  "concepts": an array of the mathematical concepts the page touches '
    '(e.g. ["tangent space", "smooth atlas"]).\n'
    "If the page is unreadable, return the object with empty values."
)


def _strip_code_fences(text: str) -> str:
    """Strip a leading/trailing ``` or ```json fence if the model added one."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _coerce_page(raw_text: str, image_ref: str, page_index: int) -> ParsedPage:
    """Parse the interpreter's text into a `ParsedPage`, tolerantly.

    The vision helper returns free text; we ask it for JSON. If the parse
    fails, stash the raw text on `text` so a bad parse never loses content
    or crashes the ingest — page parsing is enrichment, not the core path.
    """
    try:
        # `strict=False` tolerates the literal newlines/tabs the vision model
        # routinely leaves inside string values (a multi-line page
        # transcription) — strict parsing rejects those control characters and
        # would drop us into the raw-text fallback, losing `concepts`.
        data = json.loads(_strip_code_fences(raw_text), strict=False)
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        concepts = data.get("concepts") or []
        if not isinstance(concepts, list):
            concepts = [concepts]
        return ParsedPage(
            page_index=page_index,
            image_ref=image_ref,
            text=(data.get("text") or None),
            latex=(data.get("latex") or None),
            diagram_description=(data.get("diagram_description") or None),
            concepts=[str(c) for c in concepts],
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return ParsedPage(
            page_index=page_index, image_ref=image_ref, text=(raw_text or None)
        )


def _compose_ocr_text(pages: list[ParsedPage]) -> Optional[str]:
    """Combine the parsed pages into the note-level `ocr_text` blob."""
    chunks: list[str] = []
    for p in pages:
        parts = [x for x in (p.text, p.latex, p.diagram_description) if x]
        if parts:
            chunks.append("\n".join(parts))
    return "\n\n".join(chunks) if chunks else None


# Instructions for the validate_latex tool loop. Mirrors math_qa's
# `GenerateLatexStep`: the agent MUST round-trip its LaTeX through the tool
# (KaTeX in the math-ui server) and only finish once it returns valid.
class _PageLatex(BaseModel):
    """Agent output: KaTeX-validated LaTeX for one page's math."""

    latex_source: str = Field(
        default="", description="KaTeX-compilable LaTeX for the page's math (empty if none)."
    )
    validation_attempts: int = Field(
        default=1, ge=0, description="How many validate_latex calls before converging."
    )


_LATEX_INSTRUCTIONS = (
    "You are given the mathematical content of one page of handwritten study "
    "notes — possibly as unicode math symbols or rough LaTeX. Produce a single "
    "KaTeX-compilable LaTeX representation of the math on the page (use "
    "\\(...\\) / \\[...\\] delimiters around each expression). You MUST call "
    "the `validate_latex` tool and only finish once it returns valid=true; if "
    "it returns an error, fix the offending LaTeX and call it again. Put the "
    "validated LaTeX in `latex_source` and the number of validate_latex calls "
    "in `validation_attempts`. If the page has no real mathematical content, "
    "return an empty `latex_source`."
)


async def _validated_latex(page: ParsedPage, log) -> tuple[Optional[str], int]:
    """Return KaTeX-validated LaTeX for `page` (or `None`), via a
    `validate_latex` tool loop — never a guess.

    Feeds the page's extracted LaTeX (or, failing that, its transcribed
    text, which often carries the math as unicode) to a `basic_agent` that
    self-corrects against the math-ui KaTeX endpoint. Stored LaTeX is thus
    guaranteed to compile. If the agent or the UI is unavailable (e.g. the
    math-ui server isn't reachable from the worker) we store **no** LaTeX
    rather than an unvalidated guess — page parsing is best-effort
    enrichment and must not fail the ingest.
    """
    source = (page.latex or page.text or "").strip()
    if not source:
        return None, 0
    try:
        # Lazy imports: keep workflow.py importable from the control plane /
        # any runtime; pydantic_ai + basic_agent live in the default base.
        from pydantic_ai import Tool

        from ai_platform.ai.providers.basic_agent import basic_agent
        from mathai.math_notes.tools import validate_latex

        agent = basic_agent(
            output_type=_PageLatex,
            instructions=_LATEX_INSTRUCTIONS,
            tools=[Tool(validate_latex)],
            retries=2,
        )
        result = await agent.run(user_prompt=source)
        out = result.output
        return (out.latex_source.strip() or None), out.validation_attempts
    except Exception as exc:  # noqa: BLE001 — enrichment must never fail ingest
        await log.warning(f"latex validation unavailable ({exc}); storing no latex")
        return None, 0


@dataclass
class ParsePagesStep(
    BaseNode[MathNotesState, MathNotesWorkflowDependencies, MathNotesState]
):
    """Vision-parse each notebook photo into a `ParsedPage` (best-effort).

    No-ops when there are no `image_refs` or no `image_interpreter` is wired
    (the platform vision helper may not be deployed yet) — page parsing is
    enrichment, never a hard dependency of the audio ingest.
    """

    stage_label = "Parse pages"
    stage_description = "Vision-parse notebook photos into structured note pages"

    async def run(
        self, ctx: GraphRunContext[MathNotesState, MathNotesWorkflowDependencies]
    ) -> End[MathNotesState]:
        log = ctx.deps.logger.for_stage("ParsePagesStep")
        interpreter = ctx.deps.image_interpreter
        refs = ctx.state.image_refs

        if interpreter is None or not refs:
            reason = "no image_interpreter wired" if interpreter is None else "no photos"
            await log.info(f"skipping page parse ({reason})")
            return End(ctx.state)

        await log.info(f"parsing {len(refs)} page(s)")

        def _parse(image_ref: str, page_index: int) -> ParsedPage:
            # Blocking (HTTP download + vision call); runs in a worker thread.
            result = interpreter.interpret(image_ref, prompt=_PAGE_PROMPT)
            return _coerce_page(result.text, image_ref, page_index)

        async def _process(image_ref: str, page_index: int) -> ParsedPage:
            page = await asyncio.to_thread(_parse, image_ref, page_index)
            # Replace the vision model's raw LaTeX with KaTeX-validated LaTeX
            # (or None) — the math is checked against the math-ui renderer, not
            # trusted blind.
            page.latex, _attempts = await _validated_latex(page, log)
            return page

        pages = await asyncio.gather(
            *(_process(ref, i) for i, ref in enumerate(refs))
        )
        ctx.state.pages = list(pages)
        ctx.state.ocr_text = _compose_ocr_text(ctx.state.pages)
        await log.info(
            f"parsed {len(ctx.state.pages)} page(s); "
            f"{sum(len(p.concepts) for p in ctx.state.pages)} concept mention(s); "
            f"{sum(1 for p in ctx.state.pages if p.latex)} with validated LaTeX"
        )
        return End(ctx.state)


math_notes_graph = Graph(
    nodes=(TranscribeNoteStep, ParsePagesStep),
    state_type=MathNotesState,
)

math_notes_node_registry: dict[str, type] = {
    "TranscribeNoteStep": TranscribeNoteStep,
    "ParsePagesStep": ParsePagesStep,
}


def _extract_math_notes_result(state: MathNotesState):
    """Cheap preview built from end-state. The canonical result is rebuilt by
    `_fetch_result` (control.py) from the workspace artifact store."""
    from mathai.math_notes.artifacts import DailyNoteArtifact
    from mathai.math_notes.models import MathNotesResult

    if state.audio_ref is None or state.note_date is None:
        return MathNotesResult()
    note = DailyNoteArtifact(
        note_date=state.note_date,
        created_by=state.created_by,
        storage_ref=state.audio_ref,
        image_refs=state.image_refs,
        transcript=state.transcript,
        ocr_text=state.ocr_text,
    )
    # `_run_persist` has already extended `state.artifact_refs` with the minted
    # DailyNoteArtifact id by the time this runs (job_runner: persist → extract
    # → complete). Pass it through so `GET /jobs/{id}/result` can hydrate the
    # canonical artifact via `hydrate_artifact_refs` — an ungated single-node
    # job has no resume checkpoint, so this result payload is the only ref
    # source. (Hard-coding `[]` here, as the _demo template does, leaves the
    # result unable to find the artifact.)
    return MathNotesResult(
        note=note,
        artifact_refs=[str(x) for x in state.artifact_refs],
    )

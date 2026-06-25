"""Math-notes ingest graph — transcribe, extract, synthesize.

Three nodes, split into faithful **extraction** then holistic **synthesis**:

    TranscribeNoteStep → ExtractPagesStep → SynthesizeNoteStep → End

`TranscribeNoteStep` transcribes the voice note (platform `AudioInterpreter`).
`ExtractPagesStep` vision-transcribes each notebook photo *faithfully* — raw
text only, zero interpretation (no LaTeX, no concepts). `SynthesizeNoteStep`
then runs ONE holistic Opus pass over the transcript + every page's raw text
and reconstructs the intended math as a note-level `NoteSynthesis` — a
semantic neighbour of the (fuzzy) notes, not a blind mirror, KaTeX-validated.

The synthesis is factored into `synthesize_note()` so the live node AND the
data migration (`scripts/migrate_notes_to_document.py`) call the same code.

The OpenAI SDK ships in the worker base and the interpreters are platform
provider helpers, so this domain pulls no media-AI dependency of its own;
synthesis uses the platform `basic_agent` (pydantic_ai + Anthropic), imported
lazily. Heavy work (HTTP download + model calls) is offloaded to threads.
Extraction and synthesis are best-effort enrichment: they degrade (store
less) rather than fail the audio ingest. See `docs/daily-notes-redesign.md`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_notes.artifacts import NotePage, NoteSynthesis
from mathai.math_notes.state import MathNotesState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ai_platform.ai.providers.audio import AudioInterpreter
    from ai_platform.ai.providers.vision import ImageInterpreter

# The synthesis model — Claude Opus 4.8, the latest Opus (1M context). One
# call per note (not per photo), so the deeper reasoning is affordable.
SYNTHESIS_MODEL = "claude-opus-4-8"


@dataclass
class MathNotesWorkflowDependencies:
    """Per-run inputs for the math_notes graph.

    `note_date` arrives as an ISO date string from the JSON submit payload
    (or None); the node resolves it to a `date`, defaulting to today. The
    `interpreter` is the platform's `AudioInterpreter` and `image_interpreter`
    its `ImageInterpreter` (both built once per worker, over a
    `PlatformSession`); `image_interpreter` is `None` until the vision helper
    is deployed, in which case page extraction is skipped. `interpreter` is
    `None` only in degenerate/test paths.

    `page_instructions` (the faithful-extraction vision prompt) and
    `synthesis_instructions` (the silent-corrector synthesis prompt) are
    pulled from the platform `PromptRegistry` at submit time (in
    `deps_factory`) so nodes never carry hardcoded prompt strings — the
    prompts live as versioned `instructions/*.md` files (deployed via
    `aiplatform deploy-prompts`). Either is `None` on a registry miss: the
    vision call then falls back to the platform's generic prompt and the
    synthesis agent runs without system instructions — both degrade rather
    than fail the ingest.
    """

    audio_ref: str = ""
    image_refs: list[str] = field(default_factory=list)
    note_date: Optional[str] = None
    created_by: Optional[str] = None
    interpreter: Optional["AudioInterpreter"] = None
    image_interpreter: Optional["ImageInterpreter"] = None
    page_instructions: Optional[str] = None
    synthesis_instructions: Optional[str] = None
    # Resolved flair directive bodies (loaded from the registry per the note's
    # `flairs` in deps_factory) — injected into the synthesis prompt as
    # learner directives that override the silent-corrector default.
    flair_directives: list[str] = field(default_factory=list)
    logger: WorkerLogger = field(default_factory=NullLogger)


@dataclass
class TranscribeNoteStep(
    BaseNode[MathNotesState, MathNotesWorkflowDependencies, MathNotesState]
):
    """Transcribe the uploaded voice note; record it (+ refs + date) on state."""

    stage_label = "Transcribe note"
    stage_description = "Transcribe the voice note (OpenAI) onto state"

    async def run(
        self, ctx: GraphRunContext[MathNotesState, MathNotesWorkflowDependencies]
    ) -> "ExtractPagesStep":
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
        return ExtractPagesStep()


# The faithful-extraction vision prompt lives in `instructions/page_parse.md`
# (prompt `math_notes.page_parse`), loaded from the platform `PromptRegistry`
# and threaded in as `page_instructions`. It asks ONLY for a faithful
# transcription of the page — interpretation (LaTeX, concepts) is deferred to
# the holistic synthesis pass, per the §13 boundary.
@dataclass
class ExtractPagesStep(
    BaseNode[MathNotesState, MathNotesWorkflowDependencies, MathNotesState]
):
    """Faithfully transcribe each notebook photo into a `NotePage` (raw text).

    No-ops when there are no `image_refs` or no `image_interpreter` is wired —
    page extraction is enrichment, never a hard dependency of the audio ingest.
    Zero interpretation here: just capture what's on the page; the synthesis
    pass reconstructs the math.
    """

    stage_label = "Extract pages"
    stage_description = "Faithfully transcribe notebook photos (raw text, no interpretation)"

    async def run(
        self, ctx: GraphRunContext[MathNotesState, MathNotesWorkflowDependencies]
    ) -> "SynthesizeNoteStep":
        log = ctx.deps.logger.for_stage("ExtractPagesStep")
        interpreter = ctx.deps.image_interpreter
        refs = ctx.state.image_refs

        if interpreter is None or not refs:
            reason = "no image_interpreter wired" if interpreter is None else "no photos"
            await log.info(f"skipping page extraction ({reason})")
            return SynthesizeNoteStep()

        await log.info(f"extracting {len(refs)} page(s)")
        page_prompt = ctx.deps.page_instructions  # None → generic vision prompt

        def _extract(image_ref: str, page_index: int) -> NotePage:
            # Blocking (HTTP download + vision call); runs in a worker thread.
            result = interpreter.interpret(image_ref, prompt=page_prompt)
            return NotePage(
                page_index=page_index,
                image_ref=image_ref,
                raw_text=(result.text or None),
            )

        pages = await asyncio.gather(
            *(asyncio.to_thread(_extract, ref, i) for i, ref in enumerate(refs))
        )
        ctx.state.pages = list(pages)
        await log.info(
            f"extracted {len(ctx.state.pages)} page(s); "
            f"{sum(len(p.raw_text or '') for p in ctx.state.pages)} chars total"
        )
        return SynthesizeNoteStep()


# Agent output for the synthesis pass — the cleaned-up, KaTeX-validated math.
class _SynthesisOutput(BaseModel):
    """Agent output: the note-level synthesis (validated markdown + concepts)."""

    markdown: str = Field(
        default="",
        description="Prose + embedded KaTeX-compilable LaTeX for the whole note (empty if none).",
    )
    concepts: list[str] = Field(
        default_factory=list, description="Mathematical concepts the note touches."
    )
    summary: str = Field(default="", description="A short prose summary of the note.")
    validation_attempts: int = Field(
        default=1, ge=0, description="How many validate_latex calls before converging."
    )


def _compose_synthesis_prompt(
    transcript: Optional[str],
    pages: list[NotePage],
    flair_directives: Optional[list[str]] = None,
) -> Optional[str]:
    """Build the synthesis agent's user prompt from the note's raw material.

    Any `flair_directives` (resolved from the note's flairs) are prepended as a
    high-priority `LEARNER DIRECTIVES` block that overrides the synthesis
    defaults — lifting e.g. a "don't spoil" instruction out of the noisy
    transcript into a first-class control the model must obey.

    Returns `None` when there's nothing to synthesize (no transcript, no page
    text) — the caller then skips the model call entirely. Flairs alone are not
    enough to synthesize; they only steer a synthesis of real material.
    """
    # Source material first — flairs alone never trigger a synthesis.
    source_chunks: list[str] = []
    if transcript and transcript.strip():
        source_chunks.append(f"Voice-note transcript:\n{transcript.strip()}")
    page_chunks = [
        f"Page {p.page_index + 1}:\n{p.raw_text.strip()}"
        for p in pages
        if p.raw_text and p.raw_text.strip()
    ]
    if page_chunks:
        source_chunks.append(
            "Notebook pages (faithful raw transcription):\n\n" + "\n\n".join(page_chunks)
        )
    if not source_chunks:
        return None

    directives = [d.strip() for d in (flair_directives or []) if d and d.strip()]
    chunks: list[str] = []
    if directives:
        chunks.append(
            "LEARNER DIRECTIVES (these OVERRIDE your default behavior — follow "
            "them exactly):\n" + "\n\n".join(directives)
        )
    chunks.extend(source_chunks)
    return "\n\n".join(chunks)


async def synthesize_note(
    transcript: Optional[str],
    pages: list[NotePage],
    instructions: Optional[str],
    log=None,
    flair_directives: Optional[list[str]] = None,
) -> Optional[NoteSynthesis]:
    """Run the holistic synthesis pass over a note's raw material.

    Feeds the transcript + every page's faithful raw text to an Opus
    `basic_agent` that reconstructs the intended math as one coherent,
    KaTeX-validated `NoteSynthesis` — never reproducing a learner's error,
    silently producing the correct version. Returns `None` when there's
    nothing to synthesize, or when the agent / math-ui validator is
    unavailable (best-effort enrichment must never fail the ingest).

    Shared by the live `SynthesizeNoteStep` and the data migration so both
    produce identical output.
    """
    source = _compose_synthesis_prompt(transcript, pages, flair_directives)
    if not source:
        return None
    try:
        # Lazy imports: keep workflow.py importable from the control plane /
        # any runtime; pydantic_ai + basic_agent live in the default base.
        from pydantic_ai import Tool

        from ai_platform.ai.providers.basic_agent import basic_agent
        from mathai.math_notes.tools import validate_latex

        agent = basic_agent(
            model=SYNTHESIS_MODEL,
            output_type=_SynthesisOutput,
            instructions=instructions,
            tools=[Tool(validate_latex)],
            retries=2,
        )
        result = await agent.run(user_prompt=source)
        out = result.output
        return NoteSynthesis(
            markdown=(out.markdown.strip() or None),
            concepts=[str(c) for c in out.concepts],
            summary=(out.summary.strip() or None),
            model_used=SYNTHESIS_MODEL,
            validation_attempts=out.validation_attempts,
        )
    except Exception as exc:  # noqa: BLE001 — enrichment must never fail ingest
        if log is not None:
            await log.warning(f"synthesis unavailable ({exc}); storing no synthesis")
        return None


@dataclass
class SynthesizeNoteStep(
    BaseNode[MathNotesState, MathNotesWorkflowDependencies, MathNotesState]
):
    """One holistic Opus pass → the note-level `NoteSynthesis` (best-effort)."""

    stage_label = "Synthesize note"
    stage_description = "Reconstruct the intended math from the whole note (Opus)"

    async def run(
        self, ctx: GraphRunContext[MathNotesState, MathNotesWorkflowDependencies]
    ) -> End[MathNotesState]:
        log = ctx.deps.logger.for_stage("SynthesizeNoteStep")
        if ctx.deps.flair_directives:
            await log.info(f"applying {len(ctx.deps.flair_directives)} flair directive(s)")
        synthesis = await synthesize_note(
            ctx.state.transcript,
            ctx.state.pages,
            ctx.deps.synthesis_instructions,
            log,
            flair_directives=ctx.deps.flair_directives,
        )
        ctx.state.synthesis = synthesis
        if synthesis is None:
            await log.info("no synthesis produced (no source, or validator unavailable)")
        else:
            await log.info(
                f"synthesized note: {len(synthesis.markdown or '')} chars, "
                f"{len(synthesis.concepts)} concept(s), "
                f"{synthesis.validation_attempts} validate_latex call(s)"
            )
        return End(ctx.state)


math_notes_graph = Graph(
    nodes=(TranscribeNoteStep, ExtractPagesStep, SynthesizeNoteStep),
    state_type=MathNotesState,
)

math_notes_node_registry: dict[str, type] = {
    "TranscribeNoteStep": TranscribeNoteStep,
    "ExtractPagesStep": ExtractPagesStep,
    "SynthesizeNoteStep": SynthesizeNoteStep,
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
        pages=state.pages,
        synthesis=state.synthesis,
        schema_version=2,
    )
    # `_run_persist` has already extended `state.artifact_refs` with the minted
    # DailyNoteArtifact id by the time this runs (job_runner: persist → extract
    # → complete). Pass it through so `GET /jobs/{id}/result` can hydrate the
    # canonical artifact — an ungated single-node-style job has no resume
    # checkpoint, so this result payload is the only ref source.
    return MathNotesResult(
        note=note,
        artifact_refs=[str(x) for x in state.artifact_refs],
    )

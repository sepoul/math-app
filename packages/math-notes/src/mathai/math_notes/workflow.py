"""Math-notes ingest graph — transcribe, extract, assess, synthesize.

Four nodes: faithful **extraction**, then a cheap **assess/triage**, then
holistic **synthesis**:

    TranscribeNoteStep → ExtractPagesStep → AssessNoteStep → SynthesizeNoteStep → End

`TranscribeNoteStep` transcribes the voice note (platform `AudioInterpreter`).
`ExtractPagesStep` vision-transcribes each notebook photo *faithfully* — raw
text only, zero interpretation (no LaTeX, no concepts). `AssessNoteStep` runs a
CHEAP model over the transcript + page text and produces a `SynthesisPlan`
(topics, depth tier, segment boundaries, stated study scope) — the authoritative
content-density read that S4 will use to scale synthesis. `SynthesizeNoteStep`
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
from typing import TYPE_CHECKING, Optional, get_args

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_notes.artifacts import (
    DensityTier,
    NoteMagnitude,
    NotePage,
    NoteSection,
    NoteSynthesis,
    PlanTopic,
    SynthesisPlan,
    TopicKind,
)
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
    # Optional override for the assess/triage prompt. `None` (the default — the
    # `deps_factory` doesn't set it) falls back to the inline `ASSESS_INSTRUCTIONS`
    # constant, so the triage pass needs no prompt-registry entry to work. Kept as
    # a seam so the wording can later move to the registry like the others.
    assess_instructions: Optional[str] = None
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
        duration_seconds: Optional[float] = None
        if ctx.deps.interpreter is not None and ctx.deps.audio_ref:
            # Blocking work (HTTP download + OpenAI). Offload to a thread so the
            # graph's event loop isn't blocked.
            result = await asyncio.to_thread(
                ctx.deps.interpreter.transcribe, ctx.deps.audio_ref
            )
            # Keep the whole TranscriptionResult, not just `.text`: `.duration`
            # is a (minor) magnitude signal we'd otherwise discard. Often None —
            # the default transcription model doesn't surface it.
            transcript = result.text
            duration_seconds = result.duration
            await log.info(
                f"transcribed {len(transcript)} chars"
                + (f", {duration_seconds:.1f}s audio" if duration_seconds else "")
            )

        ctx.state.audio_ref = ctx.deps.audio_ref
        ctx.state.image_refs = ctx.deps.image_refs
        ctx.state.transcript = transcript
        ctx.state.audio_duration_seconds = duration_seconds
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
    ) -> "AssessNoteStep":
        log = ctx.deps.logger.for_stage("ExtractPagesStep")
        interpreter = ctx.deps.image_interpreter
        refs = ctx.state.image_refs

        if interpreter is None or not refs:
            reason = "no image_interpreter wired" if interpreter is None else "no photos"
            await log.info(f"skipping page extraction ({reason})")
        else:
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

        # Both modalities are now on state — fuse them (with audio duration)
        # into the one magnitude signal. `image_ref_count` keeps page_count
        # honest when extraction was skipped (no vision helper) but photos exist.
        ctx.state.magnitude = NoteMagnitude.from_signals(
            transcript=ctx.state.transcript,
            pages=ctx.state.pages,
            image_ref_count=len(ctx.state.image_refs),
            duration_seconds=ctx.state.audio_duration_seconds,
        )
        return AssessNoteStep()


# Agent output for the synthesis pass — the cleaned-up, KaTeX-validated math.
class _SynthesisOutput(BaseModel):
    """Agent output: the note-level synthesis (validated markdown + concepts).

    `sections` and `depth_tier` are the enrichment seam (epic #14, S5): the
    model *may* return per-topic sections and the depth it rendered at. Both
    default empty/None, so the contract is back-compatible with the current
    synthesis prompt (which asks only for the flat fields) — the prompt that
    actually drives sectioned output ships with the adaptive pass (S4, #18).
    `magnitude` is NOT here: it is measured from the note's signals, not
    produced by the model, and is embedded onto `NoteSynthesis` by the caller.
    """

    markdown: str = Field(
        default="",
        description="Prose + embedded KaTeX-compilable LaTeX for the whole note (empty if none).",
    )
    concepts: list[str] = Field(
        default_factory=list, description="Mathematical concepts the note touches."
    )
    summary: str = Field(default="", description="A short prose summary of the note.")
    sections: list[NoteSection] = Field(
        default_factory=list,
        description="Per-topic sections for a multi-topic note (empty for a short note).",
    )
    depth_tier: Optional[DensityTier] = Field(
        default=None,
        description="Depth the synthesis rendered at (brief|standard|deep); omit if unsure.",
    )
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
    *,
    magnitude: Optional[NoteMagnitude] = None,
) -> Optional[NoteSynthesis]:
    """Run the holistic synthesis pass over a note's raw material.

    Feeds the transcript + every page's faithful raw text to an Opus
    `basic_agent` that reconstructs the intended math as one coherent,
    KaTeX-validated `NoteSynthesis` — never reproducing a learner's error,
    silently producing the correct version. Returns `None` when there's
    nothing to synthesize, or when the agent / math-ui validator is
    unavailable (best-effort enrichment must never fail the ingest).

    `magnitude` (when the caller has measured it) is embedded on the result and
    seeds `depth_tier` when the model didn't pick one — so the synthesis carries
    the density signal it was scaled to. Keyword-only and optional, so the
    migration's positional call is unaffected.

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
        # Normalize the model's sections — drop fully-empty ones, strip text.
        sections = [
            NoteSection(
                heading=sec.heading.strip(),
                markdown=sec.markdown.strip(),
                concepts=[str(c) for c in sec.concepts],
            )
            for sec in out.sections
            if (sec.heading or "").strip()
            or (sec.markdown or "").strip()
            or sec.concepts
        ]
        # Carry the depth the model rendered at; fall back to the measured
        # density tier so a synthesis always reports a depth when we know one.
        depth_tier = out.depth_tier or (magnitude.density_tier if magnitude else None)
        return NoteSynthesis(
            markdown=(out.markdown.strip() or None),
            concepts=[str(c) for c in out.concepts],
            summary=(out.summary.strip() or None),
            sections=sections,
            depth_tier=depth_tier,
            magnitude=magnitude,
            model_used=SYNTHESIS_MODEL,
            validation_attempts=out.validation_attempts,
        )
    except Exception as exc:  # noqa: BLE001 — enrichment must never fail ingest
        if log is not None:
            await log.warning(f"synthesis unavailable ({exc}); storing no synthesis")
        return None


# --- assess / triage pass (S3) -----------------------------------------------

# The assess/triage model — a CHEAP read of the note *before* synthesis. Claude
# Haiku 4.5 (`claude-haiku-4-5`): the assessment is a lightweight structured read
# of a short (2–7 min) transcript + a few pages of text — enumerate the distinct
# topics, pick a depth tier, note any stated study scope — NOT the deep
# reconstruction the Opus synthesis pass does, so the cheapest current model is
# the right tier. At ~$1/$5 per MTok it is ~5× cheaper in/out than the Opus
# synthesis call, and the pass adds just one short call per note. See the PR for
# the full cost rationale.
ASSESS_MODEL = "claude-haiku-4-5"

# Inline default prompt for the assessor. Kept in-module (not in the prompt
# registry) so the triage pass is self-contained and needs no deploy-prompts
# step; `deps.assess_instructions` can override it later without a code change.
ASSESS_INSTRUCTIONS = """You triage a learner's daily math study notes.

You are given the raw material from ONE study session: a voice-note transcript \
and/or faithful transcriptions of notebook pages. You do NOT rewrite or correct \
the math — a separate pass does that. Your only job is to READ the material and \
plan how it should be written up.

A note is short (the learner spoke for a few minutes) but may summarize anywhere \
from a few minutes to several hours of study. Judge how much it contains by its \
CONTENT — how many distinct topics/problems, how much math, how many pages — not \
by length alone.

Produce:
- topics: every distinct topic, problem, or thread the session covers. For each, \
give a short title, a kind (one of: exercise, concept, proof, definition, \
example, dead_end, breakthrough, review, other), and a span_hint saying where it \
appears (e.g. "transcript opening", "pages 1-2").
- depth_tier: how deep the write-up should go — "brief" (a light or single-topic \
note), "standard" (a typical session), or "deep" (a dense, multi-topic, or long \
session).
- suggested_sections: how many sections the write-up should have (>= 1; roughly \
one per major topic).
- segment_boundaries: short cues marking natural transitions between topics, for \
splitting a long note into chunks. Leave empty for a single-topic note.
- study_scope_hint: if the learner STATES how long or how much they studied \
(e.g. "I spent the afternoon on this, about 4 hours"), capture it here. Leave \
empty if unstated.
- rationale: one or two sentences on why you chose this depth and structure.

Be faithful to what is actually there. A terse single-exercise note is "brief" \
with one topic; do not invent topics or inflate depth."""


# Lenient agent output — plain strings/ints with defaults so a slightly
# off-shape model response still parses; `_plan_from_output` then normalizes it
# into the typed `SynthesisPlan` contract.
class _AssessTopic(BaseModel):
    title: str = Field(default="", description="Short title for the topic.")
    kind: str = Field(default="other", description="Kind of material (exercise, concept, …).")
    span_hint: str = Field(default="", description="Where in the note it appears.")


class _AssessOutput(BaseModel):
    """Agent output for the triage pass — the raw plan before normalization."""

    topics: list[_AssessTopic] = Field(default_factory=list)
    depth_tier: str = Field(default="standard", description="brief | standard | deep.")
    suggested_sections: int = Field(default=1, description="Sections the synthesis should have.")
    segment_boundaries: list[str] = Field(default_factory=list)
    study_scope_hint: str = Field(default="", description="Stated study scope, if any.")
    rationale: str = Field(default="", description="Why this depth/structure.")


_VALID_DEPTH_TIERS = set(get_args(DensityTier))  # {"brief", "standard", "deep"}
_VALID_TOPIC_KINDS = set(get_args(TopicKind))


def _clean(value: Optional[str]) -> Optional[str]:
    """Trim a string; map empty/whitespace to None (the "unstated" sentinel)."""
    value = (value or "").strip()
    return value or None


def _plan_from_output(out: "_AssessOutput", model: str) -> SynthesisPlan:
    """Normalize the lenient agent output into the typed `SynthesisPlan`.

    Clamps `depth_tier`/`kind` to their valid sets (unknown → standard / other),
    floors `suggested_sections` at 1, drops blank topics/boundaries, and stamps
    `model_used`. Pure — no engine deps — so it is unit-testable without a model
    call.
    """
    topics: list[PlanTopic] = []
    for t in out.topics:
        title = (t.title or "").strip()
        if not title:
            continue
        kind = (t.kind or "other").strip().lower()
        if kind not in _VALID_TOPIC_KINDS:
            kind = "other"
        topics.append(PlanTopic(title=title, kind=kind, span_hint=_clean(t.span_hint)))

    depth = (out.depth_tier or "").strip().lower()
    if depth not in _VALID_DEPTH_TIERS:
        depth = "standard"

    sections = out.suggested_sections if isinstance(out.suggested_sections, int) else 1
    sections = max(sections, 1)

    boundaries = [b.strip() for b in (out.segment_boundaries or []) if b and b.strip()]

    return SynthesisPlan(
        topics=topics,
        depth_tier=depth,  # type: ignore[arg-type] — normalized to a valid DensityTier
        suggested_sections=sections,
        segment_boundaries=boundaries,
        study_scope_hint=_clean(out.study_scope_hint),
        rationale=_clean(out.rationale),
        model_used=model,
    )


async def _run_assess_agent(
    source: str, instructions: Optional[str], model: str
) -> "_AssessOutput":
    """Run the cheap triage agent over the note's raw material.

    Isolated from `assess_note` so tests can stub the model call, and so the
    `pydantic_ai` / `basic_agent` import stays lazy (off the control plane)."""
    from ai_platform.ai.providers.basic_agent import basic_agent

    agent = basic_agent(
        model=model,
        output_type=_AssessOutput,
        instructions=instructions,
        retries=1,
    )
    result = await agent.run(user_prompt=source)
    return result.output


async def assess_note(
    transcript: Optional[str],
    pages: list[NotePage],
    instructions: Optional[str] = None,
    log=None,
    model: str = ASSESS_MODEL,
) -> Optional[SynthesisPlan]:
    """Cheaply READ a note and produce a `SynthesisPlan` (best-effort triage).

    Runs a CHEAP model over the same transcript + page text the synthesis pass
    sees and returns how the note should be written up: distinct topics, a depth
    tier, segment boundaries, and any study scope the learner stated. This is the
    authoritative density read (S3) — a short note can summarize hours of study,
    which duration can't reveal.

    Returns `None` when there's nothing to assess, or on ANY failure — never
    raises (mirrors `synthesize_note`'s degrade pattern), so it can never fail
    the ingest; the caller then falls back to current single-pass synthesis.
    Shared by the live `AssessNoteStep` and tests.
    """
    # Same raw-material composition as synthesis (no flair directives — flairs
    # steer the write-up, not the triage).
    source = _compose_synthesis_prompt(transcript, pages)
    if not source:
        return None
    try:
        out = await _run_assess_agent(source, instructions or ASSESS_INSTRUCTIONS, model)
        return _plan_from_output(out, model)
    except Exception as exc:  # noqa: BLE001 — triage must never fail the ingest
        if log is not None:
            await log.warning(f"note assessment unavailable ({exc}); proceeding without a plan")
        return None


@dataclass
class AssessNoteStep(
    BaseNode[MathNotesState, MathNotesWorkflowDependencies, MathNotesState]
):
    """Cheap triage pass → a `SynthesisPlan` on state (best-effort).

    Reads the transcript + page text with a cheap model and records how the note
    should be synthesized (topics, depth tier, segments, stated study scope).
    Never fails the ingest: on any failure `assess_note` returns `None` and
    synthesis falls back to its current single-pass behavior. S4 will consume the
    plan; for now it is produced, persisted on state, and logged.
    """

    stage_label = "Assess note"
    stage_description = "Cheaply triage the note into a SynthesisPlan (topics + depth tier)"

    async def run(
        self, ctx: GraphRunContext[MathNotesState, MathNotesWorkflowDependencies]
    ) -> "SynthesizeNoteStep":
        log = ctx.deps.logger.for_stage("AssessNoteStep")
        plan = await assess_note(
            ctx.state.transcript,
            ctx.state.pages,
            ctx.deps.assess_instructions,
            log,
        )
        ctx.state.plan = plan
        if plan is None:
            await log.info("no synthesis plan produced (no source, or assessor unavailable)")
        else:
            await log.info(
                f"synthesis plan: depth={plan.depth_tier}, {len(plan.topics)} topic(s), "
                f"{plan.suggested_sections} section(s), {len(plan.segment_boundaries)} segment(s)"
                + (f"; study scope: {plan.study_scope_hint!r}" if plan.study_scope_hint else "")
                + (f" [{plan.model_used}]" if plan.model_used else "")
            )
        return SynthesizeNoteStep()


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
        mag = ctx.state.magnitude
        if mag is not None:
            await log.info(
                f"note magnitude: {mag.density_tier} "
                f"({mag.transcript_chars} transcript chars, {mag.page_count} page(s), "
                f"{mag.page_chars} page chars"
                + (f", {mag.duration_seconds:.1f}s" if mag.duration_seconds else "")
                + ")"
            )
        if ctx.deps.flair_directives:
            await log.info(f"applying {len(ctx.deps.flair_directives)} flair directive(s)")
        synthesis = await synthesize_note(
            ctx.state.transcript,
            ctx.state.pages,
            ctx.deps.synthesis_instructions,
            log,
            flair_directives=ctx.deps.flair_directives,
            magnitude=ctx.state.magnitude,
        )
        ctx.state.synthesis = synthesis
        if synthesis is None:
            await log.info("no synthesis produced (no source, or validator unavailable)")
        else:
            await log.info(
                f"synthesized note: {len(synthesis.markdown or '')} chars, "
                f"{len(synthesis.sections)} section(s), "
                f"{len(synthesis.concepts)} concept(s), "
                + (f"depth={synthesis.depth_tier}, " if synthesis.depth_tier else "")
                + f"{synthesis.validation_attempts} validate_latex call(s)"
            )
        return End(ctx.state)


math_notes_graph = Graph(
    nodes=(TranscribeNoteStep, ExtractPagesStep, AssessNoteStep, SynthesizeNoteStep),
    state_type=MathNotesState,
)

math_notes_node_registry: dict[str, type] = {
    "TranscribeNoteStep": TranscribeNoteStep,
    "ExtractPagesStep": ExtractPagesStep,
    "AssessNoteStep": AssessNoteStep,
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
        magnitude=state.magnitude,
        synthesis=state.synthesis,
        schema_version=3,
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

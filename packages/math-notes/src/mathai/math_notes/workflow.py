"""Math-notes ingest graph — transcribe a voice note + record the dated note.

A single node: it pulls the uploaded audio off the storage plane (via the
platform's `AudioInterpreter` over a `PlatformSession`), transcribes it with
OpenAI, and threads the transcript + refs + dated metadata onto state for
`_persist` to mint a `DailyNoteArtifact`.

    TranscribeNoteStep → End

The OpenAI SDK ships in the worker base and `AudioInterpreter` is a platform
provider helper, so this domain pulls **no** AI dependency of its own. The
module imports `pydantic_graph` (the light platform graph framework); the
heavy work (HTTP download + OpenAI call) is deferred to run time and offloaded
to a thread so it doesn't block the graph's event loop.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Optional

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_notes.state import MathNotesState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ai_platform.ai.providers.audio import AudioInterpreter


@dataclass
class MathNotesWorkflowDependencies:
    """Per-run inputs for the math_notes graph.

    `note_date` arrives as an ISO date string from the JSON submit payload
    (or None); the node resolves it to a `date`, defaulting to today. The
    `interpreter` is the platform's `AudioInterpreter` (built once per worker,
    over a `PlatformSession`); `None` only in degenerate/test paths.
    """

    audio_ref: str = ""
    image_refs: list[str] = field(default_factory=list)
    note_date: Optional[str] = None
    created_by: Optional[str] = None
    interpreter: Optional["AudioInterpreter"] = None
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
    ) -> End[MathNotesState]:
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
        return End(ctx.state)


math_notes_graph = Graph(
    nodes=(TranscribeNoteStep,),
    state_type=MathNotesState,
)

math_notes_node_registry: dict[str, type] = {
    "TranscribeNoteStep": TranscribeNoteStep,
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

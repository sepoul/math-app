"""Math-notes ingest graph + result extraction.

A single node, by design. The bytes are already in the storage plane
(uploaded by the UI via `POST /media`); this job just records the
`storage_ref` + dated metadata as a `DailyNoteArtifact`. No LLM, no
compute — the smarter notes work (OCR, transcription, topic-linking)
arrives as later nodes / sibling jobs.

    IngestNoteStep → End

Mirrors the `_demo` echo shape: deps → state → `_persist` mints the
artifact. The module imports `pydantic_graph` (the light platform graph
framework) but no LLM stack, so the worker can import it after the
catalog install pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_notes.state import MathNotesState


@dataclass
class MathNotesWorkflowDependencies:
    """Per-run inputs for the math_notes graph.

    `note_date` arrives as an ISO date string from the JSON submit
    payload (or None); the node resolves it to a `date`, defaulting to
    today when omitted.
    """

    storage_ref: str = ""
    content_type: Optional[str] = None
    byte_size: Optional[int] = None
    note_date: Optional[str] = None
    created_by: Optional[str] = None
    logger: WorkerLogger = field(default_factory=NullLogger)


@dataclass
class IngestNoteStep(BaseNode[MathNotesState, MathNotesWorkflowDependencies, MathNotesState]):
    """Record the uploaded blob's ref + dated metadata onto state, end."""

    stage_label = "Ingest note"
    stage_description = "Record the uploaded note (storage_ref + date) as a DailyNoteArtifact"

    async def run(
        self, ctx: GraphRunContext[MathNotesState, MathNotesWorkflowDependencies]
    ) -> End[MathNotesState]:
        log = ctx.deps.logger.for_stage("IngestNoteStep")
        resolved_date = (
            date.fromisoformat(ctx.deps.note_date) if ctx.deps.note_date else date.today()
        )
        await log.info(
            f"ingesting note for {resolved_date.isoformat()} "
            f"(ref={ctx.deps.storage_ref!r}, type={ctx.deps.content_type!r})"
        )
        ctx.state.storage_ref = ctx.deps.storage_ref
        ctx.state.content_type = ctx.deps.content_type
        ctx.state.byte_size = ctx.deps.byte_size
        ctx.state.note_date = resolved_date
        ctx.state.created_by = ctx.deps.created_by
        return End(ctx.state)


math_notes_graph = Graph(
    nodes=(IngestNoteStep,),
    state_type=MathNotesState,
)

math_notes_node_registry: dict[str, type] = {
    "IngestNoteStep": IngestNoteStep,
}


def _extract_math_notes_result(state: MathNotesState):
    """Cheap preview built from end-state (stored on `record.state.result_payload`).

    The canonical result is rebuilt by `_fetch_result` (control.py) from
    the workspace artifact store.
    """
    from mathai.math_notes.artifacts import DailyNoteArtifact
    from mathai.math_notes.models import MathNotesResult

    if state.storage_ref is None or state.note_date is None:
        return MathNotesResult()
    note = DailyNoteArtifact(
        note_date=state.note_date,
        created_by=state.created_by,
        storage_ref=state.storage_ref,
        content_type=state.content_type,
        byte_size=state.byte_size,
    )
    return MathNotesResult(note=note, artifact_refs=[])

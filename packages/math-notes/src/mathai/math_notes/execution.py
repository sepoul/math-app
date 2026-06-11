"""math_notes execution plane — graph + persistence.

Imports `pydantic_graph` (light) but no LLM stack. The worker imports
this lazily after the catalog install pass.
"""
from __future__ import annotations

from uuid import UUID

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.jobs.domain import BootstrapContext, ExecutionDomain
from ai_platform.jobs.execution_policy import (
    ExecutionPolicy,
    JobExecution,
    PersistencePolicy,
)
from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_notes.artifacts import MATH_NOTES_ARTIFACTS, DailyNoteArtifact
from mathai.math_notes.state import MathNotesState
from mathai.math_notes.workflow import (
    MathNotesWorkflowDependencies,
    _extract_math_notes_result,
    math_notes_graph,
    math_notes_node_registry,
)


# No human gates — ingest runs straight to completion.
math_notes_policy = ExecutionPolicy(gates=[])


def build_math_notes_execution(artifact_api: ArtifactService) -> JobExecution:
    def _deps_factory(payload: dict) -> MathNotesWorkflowDependencies:
        job_id = payload.get("_job_id")
        logger: WorkerLogger = WorkerLogger(job_id) if job_id else NullLogger()
        note_date = payload.get("note_date")
        return MathNotesWorkflowDependencies(
            storage_ref=payload.get("storage_ref", ""),
            content_type=payload.get("content_type"),
            byte_size=payload.get("byte_size"),
            # `note_date` may arrive as a date (Python caller) or an ISO
            # string (JSON submit); the node parses a string, so normalize.
            note_date=note_date.isoformat() if hasattr(note_date, "isoformat") else note_date,
            created_by=payload.get("created_by"),
            logger=logger,
        )

    def _persist(job_id: str, state: MathNotesState) -> list[UUID]:
        """Mint the DailyNoteArtifact once the note is recorded on state."""
        if state.storage_ref is None or state.note_date is None:
            return []
        artifact = DailyNoteArtifact(
            note_date=state.note_date,
            created_by=state.created_by,
            created_by_job=job_id,
            storage_ref=state.storage_ref,
            content_type=state.content_type,
            byte_size=state.byte_size,
        )
        artifact_api.put(artifact)
        return [artifact.artifact_id]

    return JobExecution(
        name="math_notes",
        graph=math_notes_graph,
        state_type=MathNotesState,
        start_node_key="IngestNoteStep",
        node_registry=math_notes_node_registry,
        deps_factory=_deps_factory,
        extract_result=_extract_math_notes_result,
        policy=math_notes_policy,
        persistence=PersistencePolicy(on_complete=_persist),
    )


def register_execution(ctx: BootstrapContext) -> ExecutionDomain:
    return ExecutionDomain(
        name="math_notes",
        job_executions=[build_math_notes_execution(ctx.artifact_service)],
        artifact_types=list(MATH_NOTES_ARTIFACTS.values()),
    )

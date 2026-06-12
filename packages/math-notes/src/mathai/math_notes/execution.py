"""math_notes execution plane — transcription graph + persistence.

Imports `pydantic_graph` (light) and the platform's audio provider helper. No
domain AI dependency: the `openai` SDK ships in the worker base and
`AudioInterpreter` reads the uploaded blob over a `PlatformSession` (the public
client), so this domain's `[execution]` extra stays empty. The worker imports
this after the catalog install pass.
"""
from __future__ import annotations

import os
from uuid import UUID

from ai_platform.ai.providers.audio import AudioInterpreter
from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.jobs.domain import BootstrapContext, ExecutionDomain
from ai_platform.jobs.execution_policy import (
    ExecutionPolicy,
    JobExecution,
    PersistencePolicy,
)
from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from ai_platform.session.session import PlatformSession
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

# Where the worker reaches the control plane to read media bytes. Compose sets
# this to http://api:8000; falls back to localhost for bare-metal dev.
_PLATFORM_API_URL = os.getenv("PLATFORM_API_URL", "http://localhost:8000")


def build_math_notes_execution(artifact_api: ArtifactService) -> JobExecution:
    # One session + interpreter per worker process. PlatformSession's httpx
    # client is lazy, so building it at registration (before the API is
    # necessarily reachable) is safe — the first call happens at job run.
    interpreter = AudioInterpreter(PlatformSession.connect(_PLATFORM_API_URL))

    def _deps_factory(payload: dict) -> MathNotesWorkflowDependencies:
        job_id = payload.get("_job_id")
        logger: WorkerLogger = WorkerLogger(job_id) if job_id else NullLogger()
        note_date = payload.get("note_date")
        return MathNotesWorkflowDependencies(
            audio_ref=payload.get("audio_ref", ""),
            image_refs=list(payload.get("image_refs") or []),
            # `note_date` may arrive as a date (Python caller) or an ISO string
            # (JSON submit); the node parses a string, so normalize.
            note_date=note_date.isoformat() if hasattr(note_date, "isoformat") else note_date,
            created_by=payload.get("created_by"),
            interpreter=interpreter,
            logger=logger,
        )

    def _persist(job_id: str, state: MathNotesState) -> list[UUID]:
        """Mint the DailyNoteArtifact once the note is transcribed + recorded."""
        if state.audio_ref is None or state.note_date is None:
            return []
        artifact = DailyNoteArtifact(
            note_date=state.note_date,
            created_by=state.created_by,
            created_by_job=job_id,
            storage_ref=state.audio_ref,
            image_refs=state.image_refs,
            transcript=state.transcript,
        )
        artifact_api.put(artifact)
        return [artifact.artifact_id]

    return JobExecution(
        name="math_notes",
        graph=math_notes_graph,
        state_type=MathNotesState,
        start_node_key="TranscribeNoteStep",
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

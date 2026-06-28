"""math_notes execution plane — transcription graph + persistence.

Imports `pydantic_graph` (light) and the platform's media provider helpers. No
domain AI dependency: the `openai` SDK ships in the worker base and the
`AudioInterpreter` / `ImageInterpreter` read the uploaded blobs over a
`PlatformSession` (the public client), so this domain's `[execution]` extra
stays empty. The worker imports this after the catalog install pass.

`ImageInterpreter` is imported defensively: the vision helper may not be
deployed in the worker base yet, so its absence must not break the audio
ingest — `ExtractPagesStep` no-ops while `image_interpreter` is `None`.
"""
from __future__ import annotations

import os
from typing import Optional
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
from ai_platform.workspace.client import PlatformClient
from mathai.math_notes.artifacts import MATH_NOTES_ARTIFACTS, DailyNoteArtifact
from mathai.math_notes.state import MathNotesState
from mathai.math_notes.workflow import (
    MathNotesWorkflowDependencies,
    _extract_math_notes_result,
    math_notes_graph,
    math_notes_node_registry,
)

try:  # the vision helper may not be deployed in the worker base yet
    from ai_platform.ai.providers.vision import ImageInterpreter
except ImportError:  # pragma: no cover - until vision.py ships
    ImageInterpreter = None  # type: ignore[assignment, misc]


# No human gates — ingest runs straight to completion.
math_notes_policy = ExecutionPolicy(gates=[])

# Where the worker reaches the control plane to read media bytes. Compose sets
# this to http://api:8000; falls back to localhost for bare-metal dev.
_PLATFORM_API_URL = os.getenv("PLATFORM_API_URL", "http://localhost:8000")


def build_math_notes_execution(
    artifact_api: ArtifactService,
    platform_client: PlatformClient,
) -> JobExecution:
    # One session + interpreters per worker process. PlatformSession's httpx
    # client is lazy, so building it at registration (before the API is
    # necessarily reachable) is safe — the first call happens at job run. Both
    # interpreters share the one session.
    session = PlatformSession.connect(_PLATFORM_API_URL)
    interpreter = AudioInterpreter(session)
    image_interpreter = ImageInterpreter(session) if ImageInterpreter is not None else None

    prompt_registry = getattr(platform_client, "prompt_registry", None)

    def _load_prompt(name: str) -> Optional[str]:
        """Best-effort fetch from the prompt registry; None on miss lets the
        nodes fall back (generic vision prompt / no-instruction agent) rather
        than crashing — extraction + synthesis are best-effort enrichment."""
        if prompt_registry is None:
            return None
        try:
            return prompt_registry.get_prompt(name).instructions
        except Exception:
            return None

    def _flair_directives(flairs: list) -> list[str]:
        """Resolve each note flair to its registry directive *body*.

        Flairs are stored as `math_notes.flair.<key>` prompts; we fetch the
        Markdown and strip the YAML front-matter (label/description are UI
        metadata) so only the directive body reaches the synthesis prompt.
        Best-effort: a missing/unreadable flair is skipped, never fatal."""
        from ai_platform.ai.prompts.registry import parse_frontmatter

        out: list[str] = []
        for key in flairs:
            md = _load_prompt(f"math_notes.flair.{key}")
            if not md:
                continue
            try:
                _meta, body = parse_frontmatter(md)
            except Exception:
                body = md
            if body and body.strip():
                out.append(body.strip())
        return out

    def _deps_factory(payload: dict) -> MathNotesWorkflowDependencies:
        job_id = payload.get("_job_id")
        logger: WorkerLogger = WorkerLogger(job_id) if job_id else NullLogger()
        note_date = payload.get("note_date")
        # Flairs arrive as enum *values* (e.g. "dont_spoil") over the JSON submit.
        flairs = [str(f) for f in (payload.get("flairs") or [])]
        return MathNotesWorkflowDependencies(
            audio_ref=payload.get("audio_ref", ""),
            image_refs=list(payload.get("image_refs") or []),
            # `note_date` may arrive as a date (Python caller) or an ISO string
            # (JSON submit); the node parses a string, so normalize.
            note_date=note_date.isoformat() if hasattr(note_date, "isoformat") else note_date,
            created_by=payload.get("created_by"),
            interpreter=interpreter,
            image_interpreter=image_interpreter,
            page_instructions=_load_prompt("math_notes.page_parse"),
            synthesis_instructions=_load_prompt("math_notes.synthesis"),
            flair_directives=_flair_directives(flairs),
            logger=logger,
        )

    def _persist(job_id: str, state: MathNotesState) -> list[UUID]:
        """Mint the one document `DailyNoteArtifact` (pages embedded inline)."""
        if state.audio_ref is None or state.note_date is None:
            return []
        note = DailyNoteArtifact(
            note_date=state.note_date,
            created_by=state.created_by,
            created_by_job=job_id,
            storage_ref=state.audio_ref,
            image_refs=state.image_refs,
            transcript=state.transcript,
            pages=state.pages,
            magnitude=state.magnitude,
            synthesis=state.synthesis,
            schema_version=3,
        )
        artifact_api.put(note)
        return [note.artifact_id]

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
        job_executions=[build_math_notes_execution(ctx.artifact_service, ctx.platform_client)],
        artifact_types=list(MATH_NOTES_ARTIFACTS.values()),
    )

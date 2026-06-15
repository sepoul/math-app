"""math_notes control plane — `JobControl` (schemas) + `register_control`.

Engine-free: imports models + artifacts only, never the graph engine.
The API imports this at boot, and `aiplatform declare-artifacts` imports
it to publish the artifact-type contract before the wheel/job exist.
"""
from __future__ import annotations

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.jobs.domain import BootstrapContext, ControlDomain
from ai_platform.jobs.execution_policy import JobControl
from ai_platform.jobs.result_fetcher import hydrate_artifact_refs
from mathai.math_notes.artifacts import MATH_NOTES_ARTIFACTS, DailyNoteArtifact
from mathai.math_notes.models import MathNotesInput, MathNotesResult


def build_math_notes_control(artifact_api: ArtifactService) -> JobControl:
    def _fetch_result(record) -> MathNotesResult:
        artifacts = hydrate_artifact_refs(record, artifact_api)
        note = next((a for a in artifacts if isinstance(a, DailyNoteArtifact)), None)
        return MathNotesResult(
            # artifact_id is a UUID; MathNotesResult.artifact_refs is list[str]
            # (pydantic won't coerce), so stringify.
            note=note,
            artifact_refs=[str(a.artifact_id) for a in artifacts],
        )

    return JobControl(
        name="math_notes",
        label="math_notes_ingest",
        submit_input_type=MathNotesInput,
        result_type=MathNotesResult,
        gates=[],  # no human review
        fetch_result=_fetch_result,
    )


def register_control(ctx: BootstrapContext) -> ControlDomain:
    return ControlDomain(
        name="math_notes",
        job_controls=[build_math_notes_control(ctx.artifact_service)],
        artifact_types=list(MATH_NOTES_ARTIFACTS.values()),
        runtime_selector="default",
        code_entrypoint="mathai.math_notes.execution:register_execution",
        control_entrypoint="mathai.math_notes.control:register_control",
    )

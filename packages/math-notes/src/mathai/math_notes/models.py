"""Math-notes data models — submit input + typed result for the ingest job.

The capture UI first uploads bytes to `POST /media` (getting back a
`storage_ref`) — a voice note, and optionally one or more notebook
photos — then submits this job with those refs. The job transcribes the
audio (OpenAI, via the platform's `AudioInterpreter`) and mints a
`DailyNoteArtifact` carrying the `transcript` + the blob refs. Artifacts
are only minted by jobs (there's no `POST /artifacts`), so this ingest
job is how a `DailyNoteArtifact` comes to exist.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import ConfigDict, Field

from ai_platform.jobs.input import BaseJobInput
from ai_platform.jobs.result import BaseJobResult


class MathNotesInput(BaseJobInput):
    """Submit input for a `math_notes` ingest job.

    `audio_ref` is the voice note to transcribe (a `storage_ref` from the
    `POST /media` response); `image_refs` are optional notebook photos
    captured alongside it. `note_date` defaults to today (resolved in the
    graph node) when omitted.
    """

    model_config = ConfigDict(extra="forbid")

    job_type: Literal["math_notes"] = "math_notes"
    audio_ref: str = Field(
        ..., description="storage_ref of the uploaded voice note (POST /media)."
    )
    image_refs: list[str] = Field(
        default_factory=list,
        description="Optional notebook-photo storage_refs captured with the note.",
    )
    note_date: Optional[date] = Field(None, description="Study day; defaults to today.")
    created_by: Optional[str] = Field(None, description="The learner capturing the note.")


class MathNotesResult(BaseJobResult):
    """Typed result for a `math_notes` job — the minted note, by ref."""

    model_config = ConfigDict(extra="forbid")

    job_type: Literal["math_notes"] = "math_notes"
    note: Optional["DailyNoteArtifact"] = None
    artifact_refs: list[str] = Field(default_factory=list)


# Forward-ref import — kept at the bottom to avoid a cycle at the artifact layer.
from mathai.math_notes.artifacts import DailyNoteArtifact  # noqa: E402

MathNotesResult.model_rebuild()

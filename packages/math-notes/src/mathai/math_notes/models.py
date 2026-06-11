"""Math-notes data models — submit input + typed result for the ingest job.

The capture UI first uploads bytes to `POST /media` (getting back a
`storage_ref`), then submits this job with that ref. The job is a thin
write path: artifacts are only minted by jobs (there's no
`POST /artifacts`), so this "ingest" job is how a `DailyNoteArtifact`
comes to exist.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import ConfigDict, Field

from ai_platform.jobs.input import BaseJobInput
from ai_platform.jobs.result import BaseJobResult


class MathNotesInput(BaseJobInput):
    """Submit input for a `math_notes` ingest job.

    `storage_ref` / `content_type` / `byte_size` come straight from the
    `POST /media` response. `note_date` defaults to today (resolved in
    the graph node) when omitted.
    """

    model_config = ConfigDict(extra="forbid")

    job_type: Literal["math_notes"] = "math_notes"
    storage_ref: str = Field(..., description="storage_ref returned by POST /media.")
    content_type: Optional[str] = Field(None, description="Content-type of the uploaded blob.")
    byte_size: Optional[int] = Field(None, description="Size in bytes of the uploaded blob.")
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

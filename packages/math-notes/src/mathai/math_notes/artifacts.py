"""Math-notes artifacts — the dated note a learner captures.

`DailyNoteArtifact` is a *blob-backed* artifact: the bytes (a notebook
photo, later a voice note) live in the storage plane, uploaded via
`POST /media`. The artifact only carries the `storage_ref` (+
content_type / byte_size, inherited from `BaseArtifact` — PR-1) plus
the dated/owner metadata. `GET /artifacts/{id}` hydrates `storage_ref`
into a `storage_url` the UI renders directly as an `<img src=…>`.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import Field

from ai_platform.jobs.artifact import BaseArtifact


class DailyNoteArtifact(BaseArtifact):
    """One captured study note, tied to a calendar day.

    `storage_ref` / `content_type` / `byte_size` are inherited from
    `BaseArtifact` and point at the uploaded blob. `ocr_text` /
    `transcript` are reserved for a later step (an OCR / transcription
    node in the `[execution]` extra) — the ingest job leaves them
    `None`; declaring them now keeps the artifact contract stable so
    that step doesn't force a schema migration.
    """

    artifact_type: Literal["daily_note"] = "daily_note"
    note_date: date = Field(..., description="The study day this note belongs to.")
    created_by: Optional[str] = Field(None, description="The learner who captured it.")

    # Populated later by an OCR / transcription step; None for raw captures.
    ocr_text: Optional[str] = Field(None, description="Extracted text from a photo (later).")
    transcript: Optional[str] = Field(None, description="Transcript of a voice note (later).")


MATH_NOTES_ARTIFACTS: dict[str, type[BaseArtifact]] = {
    DailyNoteArtifact.model_fields["artifact_type"].default: DailyNoteArtifact,
}

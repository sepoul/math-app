"""Math-notes artifacts — the dated note a learner captures.

`DailyNoteArtifact` is a *blob-backed* artifact: the bytes (a voice note,
optionally notebook photos) live in the storage plane, uploaded via
`POST /media`. The artifact carries the audio `storage_ref` (+
content_type / byte_size, inherited from `BaseArtifact` — PR-1), the
`transcript` the ingest job produced, optional `image_refs`, plus the
dated/owner metadata. `GET /artifacts/{id}` hydrates `storage_ref` into a
`storage_url` the UI renders directly (an `<audio src=…>`).
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import Field

from ai_platform.jobs.artifact import BaseArtifact


class DailyNoteArtifact(BaseArtifact):
    """One captured study note, tied to a calendar day.

    `storage_ref` / `content_type` / `byte_size` are inherited from
    `BaseArtifact` and point at the uploaded **audio** blob. `transcript`
    is populated by the ingest job's transcription node. `image_refs`
    holds any notebook photos captured with the note; `ocr_text` is
    reserved for a later OCR step over those images (declared now so that
    step doesn't force a schema migration).
    """

    artifact_type: Literal["daily_note"] = "daily_note"
    note_date: date = Field(..., description="The study day this note belongs to.")
    created_by: Optional[str] = Field(None, description="The learner who captured it.")

    # Notebook photos captured alongside the voice note (storage_refs).
    image_refs: list[str] = Field(
        default_factory=list, description="Attached notebook-photo storage_refs."
    )

    # Produced by the ingest job's transcription node.
    transcript: Optional[str] = Field(None, description="Transcript of the voice note.")
    # Reserved for a later OCR step over `image_refs`.
    ocr_text: Optional[str] = Field(None, description="Extracted text from photos (later).")


MATH_NOTES_ARTIFACTS: dict[str, type[BaseArtifact]] = {
    DailyNoteArtifact.model_fields["artifact_type"].default: DailyNoteArtifact,
}

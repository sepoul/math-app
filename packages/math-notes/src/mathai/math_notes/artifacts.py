"""Math-notes artifacts — the dated note a learner captures.

`DailyNoteArtifact` is a *blob-backed* artifact: the bytes (a voice note,
optionally notebook photos) live in the storage plane, uploaded via
`POST /media`. The artifact carries the audio `storage_ref` (+
content_type / byte_size, inherited from `BaseArtifact` — PR-1), the
`transcript` the ingest job produced, optional `image_refs`, plus the
dated/owner metadata. `GET /artifacts/{id}` hydrates `storage_ref` into a
`storage_url` the UI renders directly (an `<audio src=…>`).

`NotePageArtifact` is the vision parse of one notebook photo (its LaTeX,
concepts, and any diagram description), minted per `image_ref` alongside
the note by `ParsePagesStep`. `ParsedPage` is the in-flight shape that
parse produces on `MathNotesState` before `_persist` turns it into an
artifact — it is never stored on its own.
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_platform.jobs.artifact import BaseArtifact


class DailyNoteArtifact(BaseArtifact):
    """One captured study note, tied to a calendar day.

    `storage_ref` / `content_type` / `byte_size` are inherited from
    `BaseArtifact` and point at the uploaded **audio** blob. `transcript`
    is populated by the ingest job's transcription node. `image_refs`
    holds the notebook photos captured with the note; `ocr_text` is the
    combined text/LaTeX parsed from them by `ParsePagesStep`, with the
    per-photo structured detail (LaTeX, concepts, diagrams) living in the
    sibling `NotePageArtifact`s.
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
    # Combined readable transcription of `image_refs`, filled by ParsePagesStep
    # (per-photo structured detail lives in the `note_page` artifacts).
    ocr_text: Optional[str] = Field(
        None, description="Combined text/LaTeX parsed from the note's photos."
    )


class ParsedPage(BaseModel):
    """Structured vision-parse of one notebook photo.

    Held on `MathNotesState` in-flight; `_persist` turns each into a
    `NotePageArtifact`. Not an artifact itself — never stored or fetched
    on its own.
    """

    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(..., ge=0)
    image_ref: str
    text: Optional[str] = None
    latex: Optional[str] = None
    diagram_description: Optional[str] = None
    concepts: List[str] = Field(default_factory=list)


class NotePageArtifact(BaseArtifact):
    """A parsed notebook page — the vision interpretation of one photo.

    Minted per `image_ref` alongside the parent `DailyNoteArtifact`.
    `storage_ref` points at the photo (so `GET /artifacts/{id}` hydrates a
    viewable `storage_url`); `source_note_id` links back to the note. The
    structured fields (`latex`, `concepts`, …) are produced by the domain
    from the platform's *generic* `ImageInterpreter` text — the
    math-specific interpretation lives here, domain-side, per §13.
    """

    artifact_type: Literal["note_page"] = "note_page"
    note_date: date = Field(..., description="The study day this page belongs to.")
    created_by: Optional[str] = Field(None, description="The learner who captured it.")
    source_note_id: UUID = Field(..., description="Parent DailyNoteArtifact id.")
    image_ref: str = Field(..., description="storage_ref of the source photo.")
    page_index: int = Field(..., ge=0, description="Order among the note's photos.")
    text: Optional[str] = Field(None, description="Plain-text transcription of the page.")
    latex: Optional[str] = Field(None, description="Math on the page, transcribed as LaTeX.")
    diagram_description: Optional[str] = Field(
        None, description="Description of any diagram/figure on the page."
    )
    concepts: List[str] = Field(
        default_factory=list, description="Mathematical concepts the page touches."
    )


MATH_NOTES_ARTIFACTS: dict[str, type[BaseArtifact]] = {
    DailyNoteArtifact.model_fields["artifact_type"].default: DailyNoteArtifact,
    NotePageArtifact.model_fields["artifact_type"].default: NotePageArtifact,
}

"""Math-notes artifacts — the dated note a learner captures.

`DailyNoteArtifact` is a *blob-backed* document artifact: the bytes (a voice
note, optionally notebook photos) live in the storage plane, uploaded via
`POST /media`. One note → one artifact. The artifact carries the audio
`storage_ref` (+ content_type / byte_size, inherited from `BaseArtifact`),
the `transcript` the ingest produced, the raw per-photo extraction as nested
`pages` children, and the note-level `synthesis` (the cleaned-up, coherent
math). `GET /artifacts/{id}` hydrates `storage_ref` into a `storage_url` the
UI renders directly (an `<audio src=…>`).

Two phases produce it: faithful **extraction** (audio transcript + per-photo
raw transcription, no interpretation) then one holistic **synthesis** pass
(Opus, over the whole note) that reconstructs the intended math — a semantic
neighbour of the fuzzy notes, not a blind mirror. The raw extraction is kept
in the `pages` children as evidence; the synthesis is the strong-semantic
view. See `docs/daily-notes-redesign.md`.

`NotePageArtifact` is the **legacy** per-photo artifact (its own row, linked
by `source_note_id`). It is no longer minted — the page data now lives inline
on `DailyNoteArtifact.pages` — but the class stays registered so old rows
still hydrate and the migration can read them.
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_platform.jobs.artifact import BaseArtifact


class NotePage(BaseModel):
    """Faithful extraction of one notebook photo — a nested child of the note.

    Raw-only by design: `raw_text` is a faithful transcription of what's on
    the page (no LaTeX, no concepts — those are reconstructed note-level in
    `NoteSynthesis`). Held on `MathNotesState` in-flight and stored inline on
    `DailyNoteArtifact.pages`; never an artifact of its own.
    """

    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(..., ge=0)
    image_ref: str = Field(..., description="storage_ref of the source photo.")
    raw_text: Optional[str] = Field(
        None, description="Faithful plain-text transcription of the page."
    )
    diagram_description: Optional[str] = Field(
        None, description="Description of any diagram/figure on the page."
    )


class NoteSynthesis(BaseModel):
    """The note-level synthesis — one coherent, always-correct view of the math.

    Produced by the synthesis pass over the transcript + all page extractions.
    `markdown` is prose with embedded KaTeX-validated LaTeX (document mode);
    `concepts` and `summary` are note-level. Never reproduces an error the
    learner made — it reconstructs the intended math silently.
    """

    model_config = ConfigDict(extra="forbid")

    markdown: Optional[str] = Field(
        None, description="Prose + embedded KaTeX-validated LaTeX for the whole note."
    )
    concepts: List[str] = Field(
        default_factory=list, description="Mathematical concepts the note touches."
    )
    summary: Optional[str] = Field(
        None, description="A short prose summary of the note."
    )
    model_used: Optional[str] = Field(
        None, description="The model that produced the synthesis."
    )
    validation_attempts: int = Field(
        default=0, ge=0, description="How many validate_latex calls before converging."
    )


class DailyNoteArtifact(BaseArtifact):
    """One captured study note, tied to a calendar day — a self-contained document.

    `storage_ref` / `content_type` / `byte_size` are inherited from
    `BaseArtifact` and point at the uploaded **audio** blob. `transcript` is
    the voice-note transcription; `pages` holds the raw per-photo extraction
    (children); `synthesis` is the cleaned-up note-level math. `image_refs`
    holds the notebook-photo storage_refs.

    `pages`, `synthesis`, and `schema_version` are additive (optional with
    defaults) so old rows — written before the redesign — still hydrate under
    the current class. `schema_version` is the migration's idempotency marker:
    old rows default to 1; new/migrated documents are 2.
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

    # Raw faithful extraction, one per photo (nested children).
    pages: list[NotePage] = Field(
        default_factory=list, description="Raw per-photo extraction (children)."
    )
    # The note-level cleaned-up math (the strong-semantic view).
    synthesis: Optional[NoteSynthesis] = Field(
        None, description="Note-level synthesised, always-correct math."
    )

    # Combined readable transcription of `image_refs` (legacy field, kept for
    # back-compat on old rows; superseded by `pages` + `synthesis`).
    ocr_text: Optional[str] = Field(
        None, description="Legacy combined text/LaTeX parsed from the note's photos."
    )

    # Additive idempotency marker: old rows default to 1; migrated/new = 2.
    schema_version: int = Field(
        default=1, ge=1, description="Document shape version (1 = pre-redesign)."
    )


class NotePageArtifact(BaseArtifact):
    """LEGACY per-photo artifact — no longer minted, kept for back-compat.

    Before the document redesign, each photo was minted as its own
    `note_page` row linked to the parent via `source_note_id`. New ingests
    embed page data on `DailyNoteArtifact.pages` instead, but this class stays
    registered so old rows still hydrate on read and the migration
    (`scripts/migrate_notes_to_document.py`) can query them as its source.
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

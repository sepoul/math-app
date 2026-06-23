"""Math-notes graph state — threads the uploaded refs + note metadata from
input, through the transcription node (which fills `transcript`), the
extraction node (which fills `pages` with faithful per-photo text), and the
synthesis node (which fills `synthesis`), into `_persist`."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import Field

from ai_platform.jobs.base_state import BaseJobState
from mathai.math_notes.artifacts import NotePage, NoteSynthesis


class MathNotesState(BaseJobState):
    audio_ref: Optional[str] = None
    image_refs: list[str] = Field(default_factory=list)
    transcript: Optional[str] = None
    # Filled by ExtractPagesStep — faithful per-photo transcription (raw).
    pages: list[NotePage] = Field(default_factory=list)
    # Filled by SynthesizeNoteStep — the note-level cleaned-up math.
    synthesis: Optional[NoteSynthesis] = None
    note_date: Optional[date] = None
    created_by: Optional[str] = None

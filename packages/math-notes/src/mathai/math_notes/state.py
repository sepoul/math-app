"""Math-notes graph state — threads the uploaded refs + note metadata
from input, through the transcription node (which fills `transcript`) and
the page-parse node (which fills `pages` + `ocr_text`), into `_persist`."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import Field

from ai_platform.jobs.base_state import BaseJobState
from mathai.math_notes.artifacts import ParsedPage


class MathNotesState(BaseJobState):
    audio_ref: Optional[str] = None
    image_refs: list[str] = Field(default_factory=list)
    transcript: Optional[str] = None
    # Filled by ParsePagesStep from the notebook photos (best-effort).
    ocr_text: Optional[str] = None
    pages: list[ParsedPage] = Field(default_factory=list)
    note_date: Optional[date] = None
    created_by: Optional[str] = None

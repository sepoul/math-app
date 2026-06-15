"""Math-notes graph state — threads the uploaded refs + note metadata
from input, through the transcription node (which fills `transcript`),
into `_persist`."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import Field

from ai_platform.jobs.base_state import BaseJobState


class MathNotesState(BaseJobState):
    audio_ref: Optional[str] = None
    image_refs: list[str] = Field(default_factory=list)
    transcript: Optional[str] = None
    note_date: Optional[date] = None
    created_by: Optional[str] = None

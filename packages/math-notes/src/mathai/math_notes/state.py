"""Math-notes graph state — threads the uploaded blob's ref + note
metadata from input through the single ingest node into `_persist`."""
from __future__ import annotations

from datetime import date
from typing import Optional

from ai_platform.jobs.base_state import BaseJobState


class MathNotesState(BaseJobState):
    storage_ref: Optional[str] = None
    content_type: Optional[str] = None
    byte_size: Optional[int] = None
    note_date: Optional[date] = None
    created_by: Optional[str] = None

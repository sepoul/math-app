"""math_book graph state — threads the index pipeline end to end.

`BookState` carries the `book_index` job's data as it flows through the nodes:

    pdf_ref ──ParsePDF──▶ pages ──ExtractStructure──▶ nodes
            ──BuildGraph──▶ edges ──ChunkAndEmbed──▶ chunks + embedded_count

and the `book_retrieve` job's minimal state (`query`/`k`/`intent` in, `hits`
out). Both jobs share one state type (they never run in the same graph run;
the start node + fields used differ per job), mirroring how math-notes threads
a single state through its ingest graph.

Engine-adjacent but engine-free: this imports only pydantic + the domain
artifact value types, so it stays importable without the graph engine.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from ai_platform.jobs.base_state import BaseJobState
from mathai.math_book.artifacts import BookEdge, BookNode
from mathai.math_book.models import BookRetrievalHit


class BookState(BaseJobState):
    # --- shared / index input ------------------------------------------------
    book_id: Optional[str] = None
    pdf_ref: Optional[str] = None
    # Inclusive 1-based page window (start, end) when the caller sliced the book;
    # None means index the whole PDF.
    page_range: Optional[tuple[int, int]] = None

    # --- book_index pipeline (filled by the nodes, in order) -----------------
    # Filled by ParsePDF — faithful per-page text extracted from the PDF (raw).
    pages: list[str] = Field(default_factory=list)
    # Filled by ExtractStructure — the structural skeleton nodes (spike Track A).
    nodes: list[BookNode] = Field(default_factory=list)
    # Filled by BuildGraph — the grounding edges between nodes (spike Track B).
    edges: list[BookEdge] = Field(default_factory=list)
    # Filled by ChunkAndEmbed — chunk ids persisted to the domain vector table,
    # plus how many were embedded (mirrors the BookIndexArtifact manifest).
    chunk_ids: list[str] = Field(default_factory=list)
    embedded_count: int = 0
    embedding_model: Optional[str] = None

    # --- book_retrieve -------------------------------------------------------
    query: Optional[str] = None
    k: int = 8
    intent: Optional[str] = None
    # Filled by Retrieve — the ranked, source-traceable hits (spike Track C).
    hits: list[BookRetrievalHit] = Field(default_factory=list)

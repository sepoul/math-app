"""math_book data models — submit inputs + typed results for the two jobs.

Engine-free (pydantic only): imported by `control.py` at deploy/boot to derive
the API request/result union shapes. The book-RAG domain exposes two jobs:

  * `book_index`   — a PDF (a `storage_ref` from `POST /media`) → a structured
    skeleton (nodes/edges) + a chunk/embed index in the domain's own pgvector
    table. Mints a `BookStructureArtifact` + a `BookIndexArtifact`.
  * `book_retrieve` — a query over an already-indexed book → hybrid
    (lexical + vector + type/label + intent-gated graph expansion) retrieval,
    optionally Claude-reranked → ranked, source-traceable `BookRetrievalHit`s.

Heavy logic (parse/extract/graph/embed/retrieve) lands in the job issues
(#63 index / #64 retrieve); this module only fixes the *contract* those jobs
build on. See `docs/book-rag-integration/DESIGN.md`.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ai_platform.jobs.input import BaseJobInput
from ai_platform.jobs.result import BaseJobResult


# --- book_index ---------------------------------------------------------------


class PageRange(BaseModel):
    """An inclusive 1-based page window into the source PDF.

    Optional on `BookIndexInput`: omit to index the whole book. Lets a caller
    index a slice (e.g. the spike's representative `Ch1 §1–§3 + Ch7 §7`) without
    parsing the entire PDF.
    """

    model_config = ConfigDict(extra="forbid")

    start: int = Field(..., ge=1, description="First page to index (1-based, inclusive).")
    end: int = Field(..., ge=1, description="Last page to index (1-based, inclusive).")


class BookIndexInput(BaseJobInput):
    """Submit input for a `book_index` job.

    `pdf_ref` is the uploaded book PDF (a `storage_ref` from the `POST /media`
    response). `book_id` namespaces every chunk/node/edge this job produces —
    the domain pgvector table and the artifacts are all keyed on it, so a
    re-index of the same `book_id` supersedes the prior one. `page_range` is an
    optional slice; omit to index the whole book.
    """

    model_config = ConfigDict(extra="forbid")

    job_type: Literal["book_index"] = "book_index"
    pdf_ref: str = Field(
        ..., description="storage_ref of the uploaded book PDF (POST /media)."
    )
    book_id: str = Field(
        ..., description="Stable id namespacing this book's chunks/nodes/edges."
    )
    page_range: Optional[PageRange] = Field(
        None, description="Optional inclusive page window; omit to index the whole book."
    )


class BookIndexResult(BaseJobResult):
    """Typed result for a `book_index` job — the minted artifacts, by ref, plus
    a compact summary of what got indexed.

    The canonical artifacts (`BookStructureArtifact`, `BookIndexArtifact`) are
    resolved by ref; the scalar counts here are a cheap at-a-glance summary so a
    caller needn't hydrate the artifacts to know the index ran.
    """

    model_config = ConfigDict(extra="forbid")

    job_type: Literal["book_index"] = "book_index"
    book_id: Optional[str] = Field(None, description="The indexed book's id.")
    node_count: int = Field(0, ge=0, description="Structural skeleton nodes extracted.")
    edge_count: int = Field(0, ge=0, description="Skeleton edges (references/relations).")
    chunk_count: int = Field(0, ge=0, description="Chunks embedded into the vector table.")
    structure: Optional["BookStructureArtifact"] = Field(
        None, description="The minted skeleton artifact (by value, hydrated)."
    )
    index: Optional["BookIndexArtifact"] = Field(
        None, description="The minted chunk/index manifest artifact (hydrated)."
    )


# --- book_retrieve ------------------------------------------------------------

# Intent narrows how retrieval expands: e.g. `definition` favours definitional
# nodes, `proof`/`theorem` gate graph expansion along `depends_on`/`references`
# edges (spike Track C's intent-gated expansion). `None` runs the default
# hybrid mix. The concrete gating logic is #64; this is just the typed key set.
RetrievalIntent = Literal["definition", "theorem", "proof", "example", "general"]


class BookRetrieveInput(BaseJobInput):
    """Submit input for a `book_retrieve` job.

    Retrieves over the book previously indexed under `book_id`. `query` is the
    natural-language question; `k` is the number of ranked hits to return.
    `intent` optionally steers the hybrid mix / graph expansion (spike Track C).
    """

    model_config = ConfigDict(extra="forbid")

    job_type: Literal["book_retrieve"] = "book_retrieve"
    book_id: str = Field(..., description="The indexed book to retrieve over.")
    query: str = Field(..., description="Natural-language retrieval query.")
    k: int = Field(8, ge=1, le=100, description="Number of ranked hits to return.")
    intent: Optional[RetrievalIntent] = Field(
        None, description="Optional intent steering the hybrid mix / graph expansion."
    )


class BookRetrievalHit(BaseModel):
    """One ranked, source-traceable retrieval hit.

    `chunk_id` / `node_id` tie the hit back to the indexed corpus (source
    traceability was the spike's headline metric); `text` is the chunk body;
    `score` is the final (post-rerank) rank score. The traceability fields
    (`label` / `page` / `heading_path`) are the structured citation the design
    requires; `source` is the same, pre-rendered as one human-readable string the
    UI can show directly.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(..., description="Id of the retrieved chunk.")
    node_id: Optional[str] = Field(None, description="Structural node the chunk belongs to.")
    text: str = Field(..., description="The chunk body.")
    score: float = Field(..., description="Final (post-rerank) rank score.")
    label: Optional[str] = Field(None, description="Citation label (e.g. 'Theorem 7.7').")
    page: Optional[int] = Field(None, description="1-based source page, if known.")
    heading_path: list[str] = Field(
        default_factory=list, description="Breadcrumb from the book root."
    )
    source: Optional[str] = Field(
        None, description="Pre-rendered human-readable citation (heading path + label + page)."
    )


class BookRetrievalResult(BaseJobResult):
    """Typed result for a `book_retrieve` job — the ranked hits (+ echoed query)."""

    model_config = ConfigDict(extra="forbid")

    job_type: Literal["book_retrieve"] = "book_retrieve"
    book_id: Optional[str] = Field(None, description="The book retrieved over.")
    query: Optional[str] = Field(None, description="The query, echoed back.")
    hits: list[BookRetrievalHit] = Field(
        default_factory=list, description="Ranked, source-traceable hits (best first)."
    )


# Forward-ref imports — kept at the bottom to avoid a cycle at the artifact
# layer (artifacts.py imports nothing from models.py, so this is one-directional).
from mathai.math_book.artifacts import (  # noqa: E402
    BookIndexArtifact,
    BookStructureArtifact,
)

BookIndexResult.model_rebuild()

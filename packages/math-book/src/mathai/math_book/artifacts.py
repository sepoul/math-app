"""math_book artifacts — the structured products of indexing a book.

Two artifacts, both `BaseArtifact` subclasses (JSON-only; no blob-backing —
the PDF bytes stay in the storage plane, referenced by `storage_ref` on the
job input, not re-inlined here):

  * `BookStructureArtifact` — the *skeleton*: the structural graph of the book,
    `nodes` (chapters / sections / definitions / theorems / …) + `edges`
    (references / depends-on / relations) extracted in the index job. This is
    the grounding layer the retrieval job walks for intent-gated graph
    expansion (spike Track B).
  * `BookIndexArtifact` — the chunk/index *manifest*: what got chunked +
    embedded into the domain pgvector table (`math_book_chunks`), by ref. The
    vectors themselves live in the domain table (§13: the domain owns its
    vector store), NOT inline on the artifact — this artifact is the catalog of
    them, so a reader knows the book is indexed and how.

Artifacts are only minted by jobs (there is no `POST /artifacts`), so the
`book_index` job is how these come to exist. Registered in `MATH_BOOK_ARTIFACTS`
(keyed on the `artifact_type` Literal default) so `control.py` publishes their
JSON Schema for the SDK. Heavy population is #63; the shapes are fixed here.
See `docs/book-rag-integration/DESIGN.md`.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ai_platform.jobs.artifact import BaseArtifact

# Additive idempotency marker for the artifact shape, mirroring math-notes'
# `SECTIONED_SCHEMA_VERSION`. 1 = the initial scaffold contract (#60). Bumps are
# reserved for later job issues that enrich the shape (#63/#64).
BOOK_SCHEMA_VERSION = 1

# The kinds a structural node can be. Deliberately coarse for the scaffold;
# the extraction job (#63, spike Track A) may widen this set as it ports the
# real skeleton taxonomy.
NodeKind = Literal[
    "book",
    "chapter",
    "section",
    "subsection",
    "definition",
    "theorem",
    "lemma",
    "proposition",
    "corollary",
    "example",
    "remark",
    "exercise",
]

# The relations an edge can express between two nodes. `contains` is the
# structural parent→child; `references`/`depends_on` are the grounding edges
# retrieval expands along (spike Track B).
EdgeKind = Literal["contains", "references", "depends_on", "related_to"]


class BookNode(BaseModel):
    """One structural node in a book's skeleton — a nested child of the
    `BookStructureArtifact` (never an artifact of its own).

    `node_id` is stable within a `book_id` (the retrieval job's graph expansion
    and every `BookRetrievalHit.node_id` reference it). `label` is the
    human-readable citation stub (e.g. `Ch 7 §7.1`, `Definition 7.2`).
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., description="Stable id within the book.")
    kind: NodeKind = Field(..., description="Structural kind of this node.")
    label: Optional[str] = Field(
        None, description="Human-readable citation stub (e.g. 'Ch 7 §7.1')."
    )
    title: Optional[str] = Field(None, description="Node title/heading text.")
    page: Optional[int] = Field(None, ge=1, description="1-based source page, if known.")


class BookEdge(BaseModel):
    """One directed relation between two `BookNode`s — a nested child of the
    `BookStructureArtifact`.

    `source`/`target` are `BookNode.node_id`s. `kind` says what the relation is
    (`contains` for structure; `references`/`depends_on` for the grounding graph
    retrieval expands along).
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Source node_id.")
    target: str = Field(..., description="Target node_id.")
    kind: EdgeKind = Field(..., description="Relation kind.")


class BookStructureArtifact(BaseArtifact):
    """The structural skeleton of one indexed book — nodes + edges.

    Minted by the `book_index` job (extraction ← spike Track A, graph ← Track B).
    `book_id` namespaces it; `nodes`/`edges` carry the skeleton. Populating them
    is #63; this scaffold fixes the shape so retrieval (#64) can rely on it.
    """

    artifact_type: Literal["book_structure"] = "book_structure"
    book_id: str = Field(..., description="Id of the book this skeleton belongs to.")
    title: Optional[str] = Field(None, description="Book title, if extracted.")
    nodes: list[BookNode] = Field(
        default_factory=list, description="Structural skeleton nodes."
    )
    edges: list[BookEdge] = Field(
        default_factory=list, description="Skeleton edges (structure + grounding relations)."
    )
    schema_version: int = Field(
        default=BOOK_SCHEMA_VERSION,
        ge=1,
        description="Artifact shape version (1 = initial scaffold contract).",
    )


class BookChunkRef(BaseModel):
    """A manifest entry for one embedded chunk — a nested child of the
    `BookIndexArtifact`.

    The chunk *body* + its vector live in the domain pgvector table
    (`math_book_chunks`, keyed by `book_id` + `chunk_id`); this is only the
    catalog entry (id, owning node, embedding model) so a reader can enumerate
    what was indexed without hitting the table. Never carries the raw vector.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(..., description="Id of the chunk in the domain vector table.")
    node_id: Optional[str] = Field(None, description="Structural node the chunk belongs to.")
    token_count: Optional[int] = Field(
        None, ge=0, description="Approximate token length of the chunk."
    )
    embedding_model: Optional[str] = Field(
        None, description="Embedding model used (e.g. text-embedding-3-small)."
    )


class BookIndexArtifact(BaseArtifact):
    """The chunk/index manifest for one indexed book.

    Minted by the `book_index` job after chunk+embed (platform
    `EmbeddingsInterpreter`) → persist into the domain pgvector table. Records
    *what* was indexed (`chunks`, `chunk_count`, `embedding_model`, the vector
    table name) so a reader knows the book is retrievable and how; the vectors
    themselves stay in the domain table (§13). Populating this is #63.
    """

    artifact_type: Literal["book_index"] = "book_index"
    book_id: str = Field(..., description="Id of the book this index covers.")
    chunk_count: int = Field(0, ge=0, description="Number of chunks embedded.")
    embedding_model: Optional[str] = Field(
        None, description="Embedding model used across the chunks."
    )
    vector_table: str = Field(
        "math_book_chunks",
        description="Domain pgvector table the chunks/vectors were persisted to.",
    )
    chunks: list[BookChunkRef] = Field(
        default_factory=list, description="Per-chunk manifest entries (no raw vectors)."
    )
    schema_version: int = Field(
        default=BOOK_SCHEMA_VERSION,
        ge=1,
        description="Artifact shape version (1 = initial scaffold contract).",
    )


# Registry the control plane publishes — keyed on the `artifact_type` Literal
# default (mirrors math-notes' `MATH_NOTES_ARTIFACTS`).
MATH_BOOK_ARTIFACTS: dict[str, type[BaseArtifact]] = {
    BookStructureArtifact.model_fields["artifact_type"].default: BookStructureArtifact,
    BookIndexArtifact.model_fields["artifact_type"].default: BookIndexArtifact,
}

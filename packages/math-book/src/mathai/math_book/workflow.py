"""math_book graphs — index + retrieve node skeletons (SCAFFOLD, #60).

Two graphs share `BookState`:

  * `book_index`:  ParsePDF → ExtractStructure → BuildGraph → ChunkAndEmbed → End
  * `book_retrieve`:  Retrieve → End

Every node body here is a TODO stub — this issue (#60) fixes the *shape* only.
Each stub cites the spike branch/file the real logic ports from when the job
issues (#63 index / #64 retrieve) pick it up:

  * extraction  ← `spike/extraction-skeleton`  (`spikes/book-rag/track-a/extract.py`)
  * graph       ← `spike/graph-grounding`      (`spikes/book-rag/track-b/graph_build.py`)
  * retrieval   ← `spike/hybrid-retrieval`     (`spikes/book-rag/track-c/retrieve.py`)

Heavy deps (PDF parse, the platform `EmbeddingsInterpreter`, the pgvector
helper, the Claude rerank agent) are imported under `TYPE_CHECKING` only, so
this module imports without any engine/AI/vector stack present — matching how
`math_notes.workflow` stays import-light. See `docs/book-rag-integration/DESIGN.md`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_book.state import BookState

if TYPE_CHECKING:  # pragma: no cover - typing only; never imported at runtime
    # Populated by the job issues (#63/#64). Kept behind TYPE_CHECKING so the
    # scaffold imports with only aiplatform-core present.
    from ai_platform.ai.providers.embeddings import EmbeddingsInterpreter
    from mathai.math_book.vector_store import VectorStore

# The rerank/LLM path (spike Track C) — Claude via the platform `basic_agent`.
# A constant seam only; the retrieval job (#64) wires the actual agent.
RERANK_MODEL = "claude-opus-4-8"

# Embedding model the chunk/embed step defaults to (spike Track C used
# text-embedding-3-small). The index job (#63) may make this configurable.
EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass
class BookIndexDependencies:
    """Per-run inputs for the `book_index` graph.

    `pdf_ref` / `book_id` / `page_range` come from `BookIndexInput` via the
    execution `deps_factory`. `embeddings` is the platform's
    `EmbeddingsInterpreter` (built once per worker over a `PlatformSession`,
    like math-notes' `AudioInterpreter`); `vector_store` is the domain-owned
    pgvector helper. Both are wired in #63 — `None` here in the scaffold.
    """

    pdf_ref: str = ""
    book_id: str = ""
    page_range: Optional[tuple[int, int]] = None
    embeddings: Optional["EmbeddingsInterpreter"] = None
    vector_store: Optional["VectorStore"] = None
    embedding_model: str = EMBEDDING_MODEL
    logger: WorkerLogger = field(default_factory=NullLogger)


@dataclass
class BookRetrieveDependencies:
    """Per-run inputs for the `book_retrieve` graph.

    `query` / `k` / `intent` come from `BookRetrieveInput`. `embeddings`
    embeds the query; `vector_store` runs the kNN + lexical query over the
    domain table. Rerank (Claude via `basic_agent`) is wired in #64.
    """

    book_id: str = ""
    query: str = ""
    k: int = 8
    intent: Optional[str] = None
    embeddings: Optional["EmbeddingsInterpreter"] = None
    vector_store: Optional["VectorStore"] = None
    logger: WorkerLogger = field(default_factory=NullLogger)


# --- book_index nodes ---------------------------------------------------------


@dataclass
class ParsePDF(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Parse the source PDF into faithful per-page text onto `state.pages`.

    Raw extraction only — no interpretation (structure is `ExtractStructure`'s
    job). Honors `page_range` when set.
    """

    stage_label = "Parse PDF"
    stage_description = "Extract faithful per-page text from the source PDF"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> "ExtractStructure":
        log = ctx.deps.logger.for_stage("ParsePDF")
        ctx.state.book_id = ctx.deps.book_id
        ctx.state.pdf_ref = ctx.deps.pdf_ref
        ctx.state.page_range = ctx.deps.page_range
        # TODO(#63): port PDF parse from spike/extraction-skeleton
        #   (spikes/book-rag/track-a/extract.py — the parse_runs → pages stage).
        #   Download the PDF bytes via the PlatformSession (like math_notes'
        #   AudioInterpreter reads a storage_ref), extract raw per-page text
        #   (honoring page_range), and fill ctx.state.pages. Offload the
        #   blocking parse to a worker thread (asyncio.to_thread).
        await log.info("ParsePDF stub — no-op (logic lands in #63)")
        return ExtractStructure()


@dataclass
class ExtractStructure(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Extract the structural skeleton nodes (chapters/sections/defs/theorems)
    from the parsed pages onto `state.nodes`."""

    stage_label = "Extract structure"
    stage_description = "Extract the book's structural skeleton nodes"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> "BuildGraph":
        log = ctx.deps.logger.for_stage("ExtractStructure")
        # TODO(#63): port structure extraction from spike/extraction-skeleton
        #   (spikes/book-rag/track-a/extract.py + harden.py — the toc_entries →
        #   nodes stage). Produce mathai.math_book.artifacts.BookNode values from
        #   ctx.state.pages and fill ctx.state.nodes.
        await log.info("ExtractStructure stub — no-op (logic lands in #63)")
        return BuildGraph()


@dataclass
class BuildGraph(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Build the grounding graph — reference/depends-on edges between nodes —
    onto `state.edges`."""

    stage_label = "Build graph"
    stage_description = "Build the grounding graph (reference/depends-on edges)"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> "ChunkAndEmbed":
        log = ctx.deps.logger.for_stage("BuildGraph")
        # TODO(#63): port graph grounding from spike/graph-grounding
        #   (spikes/book-rag/track-b/graph_build.py + semantic_edges.py — the
        #   node_edges/references stage). Produce BookEdge values (contains /
        #   references / depends_on) over ctx.state.nodes; fill ctx.state.edges.
        await log.info("BuildGraph stub — no-op (logic lands in #63)")
        return ChunkAndEmbed()


@dataclass
class ChunkAndEmbed(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Chunk the pages, embed each chunk (platform `EmbeddingsInterpreter`), and
    upsert into the domain pgvector table via the `VectorStore` helper.

    Records the persisted chunk ids + count on state (the `BookIndexArtifact`
    manifest is minted from these in `execution._persist`).
    """

    stage_label = "Chunk and embed"
    stage_description = "Chunk, embed (platform Embedder), and upsert to the domain vector table"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> End[BookState]:
        log = ctx.deps.logger.for_stage("ChunkAndEmbed")
        ctx.state.embedding_model = ctx.deps.embedding_model
        # TODO(#63): port chunk+embed from spike/hybrid-retrieval
        #   (spikes/book-rag/track-c/build_index.py + embed.py). Chunk
        #   ctx.state.pages/nodes, embed each chunk with the platform
        #   `EmbeddingsInterpreter` (from ai_platform.ai.providers.embeddings,
        #   added in #61 — DO NOT call it here in the scaffold), then upsert
        #   into the domain table via ctx.deps.vector_store.upsert(book_id, ...).
        #   Fill ctx.state.chunk_ids + ctx.state.embedded_count.
        await log.info("ChunkAndEmbed stub — no-op (logic lands in #63)")
        return End(ctx.state)


# --- book_retrieve node -------------------------------------------------------


@dataclass
class Retrieve(BaseNode[BookState, BookRetrieveDependencies, BookState]):
    """Hybrid retrieval over an indexed book → ranked, source-traceable hits.

    Lexical + vector + type/label + intent-gated graph expansion, then optional
    Claude rerank (`basic_agent`). Fills `state.hits`.
    """

    stage_label = "Retrieve"
    stage_description = "Hybrid retrieval (+ intent-gated graph expansion, optional rerank)"

    async def run(
        self, ctx: GraphRunContext[BookState, BookRetrieveDependencies]
    ) -> End[BookState]:
        log = ctx.deps.logger.for_stage("Retrieve")
        ctx.state.book_id = ctx.deps.book_id
        ctx.state.query = ctx.deps.query
        ctx.state.k = ctx.deps.k
        ctx.state.intent = ctx.deps.intent
        # TODO(#64): port hybrid retrieval from spike/hybrid-retrieval
        #   (spikes/book-rag/track-c/retrieve.py + rerank.py). Embed the query
        #   (platform EmbeddingsInterpreter), run lexical + vector kNN
        #   (ctx.deps.vector_store.knn_query) + type/label filters +
        #   intent-gated graph expansion over the BookStructureArtifact edges,
        #   optionally rerank the top-K with Claude via
        #   ai_platform.ai.providers.basic_agent.basic_agent(model=RERANK_MODEL),
        #   and fill ctx.state.hits with BookRetrievalHit values.
        await log.info("Retrieve stub — no-op (logic lands in #64)")
        return End(ctx.state)


# --- graphs + registries ------------------------------------------------------

book_index_graph = Graph(
    nodes=(ParsePDF, ExtractStructure, BuildGraph, ChunkAndEmbed),
    state_type=BookState,
)

book_retrieve_graph = Graph(
    nodes=(Retrieve,),
    state_type=BookState,
)

book_index_node_registry: dict[str, type] = {
    "ParsePDF": ParsePDF,
    "ExtractStructure": ExtractStructure,
    "BuildGraph": BuildGraph,
    "ChunkAndEmbed": ChunkAndEmbed,
}

book_retrieve_node_registry: dict[str, type] = {
    "Retrieve": Retrieve,
}


def _extract_book_index_result(state: BookState):
    """Cheap preview built from end-state. The canonical result is rebuilt by
    `control.build_book_index_control._fetch_result` from the artifact store."""
    from mathai.math_book.models import BookIndexResult

    return BookIndexResult(
        book_id=state.book_id,
        node_count=len(state.nodes),
        edge_count=len(state.edges),
        chunk_count=state.embedded_count,
        artifact_refs=[x for x in state.artifact_refs],
    )


def _extract_book_retrieve_result(state: BookState):
    """Cheap preview built from end-state — the ranked hits threaded on state.
    Canonical refs are surfaced by `control` from the artifact store."""
    from mathai.math_book.models import BookRetrievalResult

    return BookRetrievalResult(
        book_id=state.book_id,
        query=state.query,
        hits=list(state.hits),
        artifact_refs=[x for x in state.artifact_refs],
    )

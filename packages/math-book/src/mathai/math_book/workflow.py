"""math_book graphs — the `book_index` pipeline (#63) + the `book_retrieve` seam.

Two graphs share `BookState`:

  * `book_index`:  ParsePDF → ExtractStructure → BuildGraph → ChunkAndEmbed → End
  * `book_retrieve`:  Retrieve → End

The `book_index` nodes are implemented (#63) by reusing the spike branch code
via the domain-internal ports:

  * extraction  ← `spike/extraction-skeleton`  (`track-a/`) → `_extraction.parse_pdf`
  * graph       ← `spike/graph-grounding`      (`track-b/`) → `_graph.build_graph`
  * chunk/embed ← `spike/hybrid-retrieval`     (`track-c/`) → `_chunking.build_chunks`
                  + the platform `EmbeddingsInterpreter` + `vector_store.VectorStore`

`Retrieve` (the `book_retrieve` job) stays a stub — its hybrid + intent-gated
`_graph.expand()` + Claude rerank land in #64.

Heavy deps (PyMuPDF, psycopg/pgvector, the `EmbeddingsInterpreter`, the rerank
agent) are imported lazily inside node bodies / under `TYPE_CHECKING`, so this
module imports with only the graph engine present — matching how
`math_notes.workflow` stays import-light. See `docs/book-rag-integration/DESIGN.md`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from mathai.math_book.artifacts import BookEdge, BookNode
from mathai.math_book.state import BookState

if TYPE_CHECKING:  # pragma: no cover - typing only; never imported at runtime
    from ai_platform.ai.providers.embeddings import EmbeddingsInterpreter

    from mathai.math_book._extraction import ParsedEquation, ParsedNode
    from mathai.math_book._chunking import Chunk
    from mathai.math_book.vector_store import VectorStore

# The rerank/LLM path (spike Track C) — Claude via the platform `basic_agent`.
# A constant seam only; the retrieval job (#64) wires the actual agent.
RERANK_MODEL = "claude-opus-4-8"

# Embedding model the chunk/embed step defaults to (spike Track C used
# text-embedding-3-small — the platform Embedder's default too).
EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass
class _IndexScratch:
    """Run-scoped, non-serialized working set for the `book_index` graph.

    `BookState` only carries the serializable published outputs (`BookNode` /
    `BookEdge` + counts); the raw spike dataclasses (`ParsedNode`,
    `ParsedEquation`, `Chunk`) flow between nodes here instead of being forced
    onto pydantic state. Lives on the deps (built once per run)."""

    parsed_nodes: list = field(default_factory=list)      # list[ParsedNode]
    parsed_equations: list = field(default_factory=list)  # list[ParsedEquation]
    chunks: list = field(default_factory=list)            # list[Chunk]


@dataclass
class BookIndexDependencies:
    """Per-run inputs for the `book_index` graph.

    `pdf_ref` / `book_id` / `page_range` come from `BookIndexInput` via the
    execution `deps_factory`. `session` is the `PlatformSession` used to read the
    PDF bytes off the storage plane; `embeddings` is the platform's
    `EmbeddingsInterpreter`; `vector_store` is the domain-owned pgvector helper
    (all built once per worker). `book_title` seeds the contextualized embed
    input. `scratch` threads the raw spike dataclasses between nodes.
    """

    pdf_ref: str = ""
    book_id: str = ""
    book_title: str = ""
    page_range: Optional[tuple[int, int]] = None
    session: Optional[object] = None  # PlatformSession (duck-typed .download_media)
    embeddings: Optional["EmbeddingsInterpreter"] = None
    vector_store: Optional["VectorStore"] = None
    embedding_model: str = EMBEDDING_MODEL
    scratch: _IndexScratch = field(default_factory=_IndexScratch)
    logger: WorkerLogger = field(default_factory=NullLogger)


@dataclass
class BookRetrieveDependencies:
    """Per-run inputs for the `book_retrieve` graph.

    `query` / `k` / `intent` come from `BookRetrieveInput`. `embeddings` embeds
    the query; `vector_store` runs the vector + lexical legs over the domain
    table. `load_structure` is a callable `(book_id) -> BookStructureArtifact | None`
    the node uses to load the skeleton (nodes for source-traceability + edges for
    intent-gated graph expansion) — injected by the execution layer over the
    artifact store. `rerank` gates the Claude rerank pass.
    """

    book_id: str = ""
    query: str = ""
    k: int = 8
    intent: Optional[str] = None
    rerank: bool = True
    embeddings: Optional["EmbeddingsInterpreter"] = None
    vector_store: Optional["VectorStore"] = None
    load_structure: Optional[object] = None  # (book_id) -> BookStructureArtifact | None
    logger: WorkerLogger = field(default_factory=NullLogger)


# --- book_index nodes ---------------------------------------------------------


@dataclass
class ParsePDF(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Download the PDF off the storage plane and deterministically parse it into
    a typed skeleton (`_extraction.parse_pdf`, ported from spike Track A).

    The raw `ParsedNode`/`ParsedEquation` set is stashed on `deps.scratch` for
    the downstream nodes; the blocking work (HTTP download + PyMuPDF parse) runs
    in a worker thread. Honors `page_range` when set.
    """

    stage_label = "Parse PDF"
    stage_description = "Download + deterministically parse the PDF into a skeleton"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> "ExtractStructure":
        log = ctx.deps.logger.for_stage("ParsePDF")
        ctx.state.book_id = ctx.deps.book_id
        ctx.state.pdf_ref = ctx.deps.pdf_ref
        ctx.state.page_range = ctx.deps.page_range

        session = ctx.deps.session
        if session is None or not ctx.deps.pdf_ref:
            await log.info("ParsePDF skipped (no session or pdf_ref)")
            return ExtractStructure()

        def _download_and_parse():
            # PlatformSession.download_media(ref) -> bytes (same call the
            # EmbeddingsInterpreter/AudioInterpreter use to read a storage_ref).
            from mathai.math_book._extraction import parse_pdf

            pdf_bytes = session.download_media(ctx.deps.pdf_ref)
            return parse_pdf(pdf_bytes, ctx.deps.page_range)

        parsed_nodes, parsed_eqs = await asyncio.to_thread(_download_and_parse)
        ctx.deps.scratch.parsed_nodes = parsed_nodes
        ctx.deps.scratch.parsed_equations = parsed_eqs
        await log.info(
            f"parsed {len(parsed_nodes)} node(s), {len(parsed_eqs)} equation region(s)"
        )
        return ExtractStructure()


@dataclass
class ExtractStructure(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Map the parsed skeleton into published `BookNode`s on `state.nodes`
    (namespacing each node_id under the book_id)."""

    stage_label = "Extract structure"
    stage_description = "Map the parsed skeleton into published BookNodes"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> "BuildGraph":
        log = ctx.deps.logger.for_stage("ExtractStructure")
        book_id = ctx.deps.book_id
        nodes: list[BookNode] = []
        for n in ctx.deps.scratch.parsed_nodes:
            nodes.append(BookNode(
                node_id=f"{book_id}:{n.node_id}",
                kind=n.kind,
                parent_id=(f"{book_id}:{n.parent_id}" if n.parent_id else None),
                label=n.label,
                title=n.title,
                heading_path=list(n.heading_path or []),
                page=n.page_pdf_start,
                page_end=n.page_pdf_end,
                text=(n.text_normalized or n.text_raw or None),
                proves=(f"{book_id}:{n.proves}" if n.proves else None),
                confidence=n.confidence,
            ))
        ctx.state.nodes = nodes
        await log.info(f"structured {len(nodes)} BookNode(s)")
        return BuildGraph()


@dataclass
class BuildGraph(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Build the grounding graph over the parsed skeleton
    (`_graph.build_graph`, ported from spike Track B): contains/parent_of/
    next/previous/proven_by/has_equation + resolved references/referenced_by.
    Node ids are namespaced under book_id to match `state.nodes`.
    """

    stage_label = "Build graph"
    stage_description = "Build the grounding graph (structure + resolved references)"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> "ChunkAndEmbed":
        log = ctx.deps.logger.for_stage("BuildGraph")
        from mathai.math_book._graph import build_graph

        book_id = ctx.deps.book_id
        raw_edges = build_graph(ctx.deps.scratch.parsed_nodes)
        edges: list[BookEdge] = []
        for e in raw_edges:
            edges.append(BookEdge(
                source=f"{book_id}:{e['from_node_id']}",
                # has_equation targets are equation-region ids, not nodes — still
                # namespace them so the edge target is unambiguous.
                target=f"{book_id}:{e['to_node_id']}",
                kind=e["edge_type"],
                confidence=e.get("confidence"),
            ))
        ctx.state.edges = edges
        await log.info(f"built {len(edges)} edge(s)")
        return ChunkAndEmbed()


@dataclass
class ChunkAndEmbed(BaseNode[BookState, BookIndexDependencies, BookState]):
    """Chunk leaf+section nodes with a contextualized embed_input
    (`_chunking.build_chunks`, spike Track C), embed each via the platform
    `EmbeddingsInterpreter`, and upsert into the domain pgvector table
    (`vector_store.VectorStore`).

    Records the persisted chunk ids + embedded count on state (the
    `BookIndexArtifact` manifest is minted from these in `execution._persist`).
    Embedding + DB writes are best-effort per chunk — a single failure is logged
    and skipped rather than failing the whole index.
    """

    stage_label = "Chunk and embed"
    stage_description = "Chunk, embed (platform Embedder), upsert to the domain vector table"

    async def run(
        self, ctx: GraphRunContext[BookState, BookIndexDependencies]
    ) -> End[BookState]:
        log = ctx.deps.logger.for_stage("ChunkAndEmbed")
        model = ctx.deps.embedding_model
        ctx.state.embedding_model = model

        from mathai.math_book._chunking import build_chunks

        chunks = build_chunks(
            ctx.deps.scratch.parsed_nodes,
            book_id=ctx.deps.book_id,
            book_title=ctx.deps.book_title,
        )
        ctx.deps.scratch.chunks = chunks

        embeddings = ctx.deps.embeddings
        store = ctx.deps.vector_store
        if embeddings is None or store is None or not chunks:
            reason = ("no embeddings helper" if embeddings is None
                      else "no vector store" if store is None else "no chunks")
            await log.info(f"chunk/embed skipped ({reason}); {len(chunks)} chunk(s) built")
            ctx.state.chunk_ids = [c.chunk_id for c in chunks]
            return End(ctx.state)

        # Fresh index for this book supersedes any prior one (spike re-run wipes
        # the run's rows first).
        def _reindex():
            from mathai.math_book.vector_store import ChunkRecord

            try:
                store.delete_book(ctx.deps.book_id)
            except Exception as exc:  # pragma: no cover - best effort
                # first-index: table may not exist yet; delete_book no-ops then.
                pass
            done = 0
            for c in chunks:
                try:
                    result = embeddings.embed(c.embed_input, model=model)
                    vec = list(result.vector or [])
                    if not vec:
                        continue
                    store.upsert(ctx.deps.book_id, ChunkRecord(
                        chunk_id=c.chunk_id,
                        text=c.text,
                        embedding=vec,
                        node_id=f"{ctx.deps.book_id}:{c.node_id}",
                        source=_chunk_source(c),
                        kind=c.kind,
                        embedding_model=result.model,
                    ))
                    done += 1
                except Exception as exc:  # pragma: no cover - per-chunk best effort
                    # swallow one bad chunk; keep indexing the rest.
                    continue
            return done

        embedded = await asyncio.to_thread(_reindex)
        ctx.state.chunk_ids = [c.chunk_id for c in chunks]
        ctx.state.embedded_count = embedded
        await log.info(
            f"embedded {embedded}/{len(chunks)} chunk(s) into the domain vector table"
        )
        return End(ctx.state)


def _chunk_source(chunk: "Chunk") -> Optional[str]:
    """Human-readable citation for a chunk (heading breadcrumb + label)."""
    hp = " › ".join(chunk.heading_path or [])
    src = " ".join(x for x in (hp, chunk.label or "") if x).strip()
    return src or None


# --- book_retrieve node -------------------------------------------------------


def _edges_for_expand(structure) -> list[dict]:
    """Convert `BookStructureArtifact.edges` (source/target/kind) into the
    `{from_node_id,to_node_id,edge_type,confidence}` dicts `_graph.expand` walks."""
    if structure is None:
        return []
    return [
        {"from_node_id": e.source, "to_node_id": e.target,
         "edge_type": e.kind, "confidence": e.confidence}
        for e in structure.edges
    ]


@dataclass
class Retrieve(BaseNode[BookState, BookRetrieveDependencies, BookState]):
    """Hybrid retrieval over an indexed book → ranked, source-traceable hits.

    The `C_full` retriever (spike Track C): min-max-fused vector + lexical +
    type/label boosts + section demotion, intent-gated graph expansion over the
    `BookStructureArtifact` edges, then an optional Claude rerank. Fills
    `state.hits` with `BookRetrievalHit`s (chunk_id + node_id + label + page +
    source). Best-effort — degrades to fewer/empty hits rather than failing.
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
        ctx.state.reranked = ctx.deps.rerank

        embeddings = ctx.deps.embeddings
        store = ctx.deps.vector_store
        if embeddings is None or store is None or not ctx.deps.query:
            reason = ("no embeddings helper" if embeddings is None
                      else "no vector store" if store is None else "empty query")
            await log.info(f"retrieve skipped ({reason})")
            return End(ctx.state)

        # Load the skeleton once: nodes (source-traceability) + edges (expansion).
        structure = None
        loader = ctx.deps.load_structure
        if loader is not None:
            try:
                structure = loader(ctx.deps.book_id)
            except Exception:  # pragma: no cover - best effort
                structure = None
        node_index = {n.node_id: n for n in structure.nodes} if structure else {}
        edges = _edges_for_expand(structure)

        def _run_retrieval():
            from mathai.math_book._retrieval import BookRetriever

            retriever = BookRetriever(
                book_id=ctx.deps.book_id,
                vector_store=store,
                embeddings=embeddings,
                edges=edges,
                node_index=node_index,
            )
            return retriever.hybrid(ctx.deps.query, k=ctx.deps.k, rerank=ctx.deps.rerank)

        cands = await asyncio.to_thread(_run_retrieval)

        from mathai.math_book.models import BookRetrievalHit

        hits = [
            BookRetrievalHit(
                chunk_id=c.chunk_id,
                node_id=c.node_id,
                text=c.text,
                score=float(c.score),
                label=c.label,
                page=c.page,
                heading_path=list(c.heading_path or []),
                source=_hit_source(c),
            )
            for c in cands
        ]
        ctx.state.hits = hits
        await log.info(
            f"retrieved {len(hits)} hit(s) "
            f"(structural_expansion={'on' if edges else 'off'}, "
            f"rerank={'on' if ctx.deps.rerank else 'off'})"
        )
        return End(ctx.state)


def _hit_source(cand) -> Optional[str]:
    """Human-readable citation for a hit: heading breadcrumb + label + page."""
    hp = " › ".join(cand.heading_path or [])
    label = cand.label or ""
    page = f"p{cand.page}" if cand.page else ""
    return " ".join(x for x in (hp, label, page) if x).strip() or None


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

"""math_book execution plane — index + retrieve graphs + persistence.

Imports `pydantic_graph` (light) and, at *runtime* (inside `build_*`, not at
module load), the platform embeddings helper + the domain vector store — so this
module stays importable with only the graph engine present, matching how
`math_notes.execution` defers its media helpers. The worker imports this after
the catalog install pass.

`book_index` (#63) is wired end to end: the `EmbeddingsInterpreter` + the domain
`VectorStore` are built once per worker and threaded into the graph deps; the
graph parses the PDF (spike Track A), builds the grounding graph (Track B),
chunks + embeds (Track C + the platform Embedder) into the domain pgvector
table, and `_persist` mints the `BookStructureArtifact` + `BookIndexArtifact`
from end-state. `book_retrieve` (#64) is still a stub. The `EmbeddingsInterpreter`
is imported defensively (its absence must not crash registration — a worker base
predating #61 would just index nothing). See `docs/book-rag-integration/DESIGN.md`.
"""
from __future__ import annotations

import os
from uuid import UUID

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.jobs.domain import BootstrapContext, ExecutionDomain
from ai_platform.jobs.execution_policy import (
    ExecutionPolicy,
    JobExecution,
    PersistencePolicy,
)
from ai_platform.runtime.worker_log import NullLogger, WorkerLogger
from ai_platform.session.session import PlatformSession
from ai_platform.workspace.client import PlatformClient
from mathai.math_book.artifacts import (
    BOOK_SCHEMA_VERSION,
    MATH_BOOK_ARTIFACTS,
    BookChunkRef,
    BookIndexArtifact,
    BookRetrievalArtifact,
    BookStructureArtifact,
    RetrievedHit,
)
from mathai.math_book.state import BookState
from mathai.math_book.workflow import (
    EMBEDDING_MODEL,
    BookIndexDependencies,
    BookRetrieveDependencies,
    _extract_book_index_result,
    _extract_book_retrieve_result,
    book_index_graph,
    book_index_node_registry,
    book_retrieve_graph,
    book_retrieve_node_registry,
)

try:  # the embeddings helper landed in the worker base with #61
    from ai_platform.ai.providers.embeddings import EmbeddingsInterpreter
except ImportError:  # pragma: no cover - worker base predating #61
    EmbeddingsInterpreter = None  # type: ignore[assignment, misc]

# No human gates — both jobs run straight to completion.
book_index_policy = ExecutionPolicy(gates=[])
book_retrieve_policy = ExecutionPolicy(gates=[])

# Where the worker reaches the control plane (media bytes, embeddings source).
# Compose sets this to http://api:8000; falls back to localhost for bare metal.
_PLATFORM_API_URL = os.getenv("PLATFORM_API_URL", "http://localhost:8000")


def build_book_index_execution(
    artifact_api: ArtifactService,
    platform_client: PlatformClient,
) -> JobExecution:
    # One session + interpreter + vector store per worker process. All are lazy
    # at construction (httpx client / DB connection open on first use), so
    # building them at registration — before the API/DB is necessarily reachable
    # — is safe; the first real use happens at job run.
    session = PlatformSession.connect(_PLATFORM_API_URL)
    embeddings = (
        EmbeddingsInterpreter(session, model=EMBEDDING_MODEL)
        if EmbeddingsInterpreter is not None else None
    )
    # Domain-owned pgvector store (connects to the tenant DB on first upsert).
    from mathai.math_book.vector_store import VectorStore

    vector_store = VectorStore()

    def _deps_factory(payload: dict) -> BookIndexDependencies:
        job_id = payload.get("_job_id")
        logger: WorkerLogger = WorkerLogger(job_id) if job_id else NullLogger()
        pr = payload.get("page_range")
        page_range = (int(pr["start"]), int(pr["end"])) if pr else None
        return BookIndexDependencies(
            pdf_ref=payload.get("pdf_ref", ""),
            book_id=payload.get("book_id", ""),
            book_title=payload.get("book_title", ""),
            page_range=page_range,
            session=session,
            embeddings=embeddings,
            vector_store=vector_store,
            embedding_model=EMBEDDING_MODEL,
            logger=logger,
        )

    def _persist(job_id: str, state: BookState) -> list[UUID]:
        """Mint the skeleton + index-manifest artifacts from end-state."""
        if not state.book_id:
            return []
        structure = BookStructureArtifact(
            created_by_job=job_id,
            book_id=state.book_id,
            nodes=state.nodes,
            edges=state.edges,
            schema_version=BOOK_SCHEMA_VERSION,
        )
        index = BookIndexArtifact(
            created_by_job=job_id,
            book_id=state.book_id,
            chunk_count=state.embedded_count,
            embedding_model=state.embedding_model,
            chunks=[
                # chunk_id is "<book_id>:<node_id>" — recover the node_id for the
                # manifest so a reader can map a chunk back to the skeleton.
                BookChunkRef(
                    chunk_id=cid,
                    node_id=(cid.split(":", 1)[1] if ":" in cid else None),
                    embedding_model=state.embedding_model,
                )
                for cid in state.chunk_ids
            ],
            schema_version=BOOK_SCHEMA_VERSION,
        )
        artifact_api.put(structure)
        artifact_api.put(index)
        return [structure.artifact_id, index.artifact_id]

    return JobExecution(
        name="book_index",
        graph=book_index_graph,
        state_type=BookState,
        start_node_key="ParsePDF",
        node_registry=book_index_node_registry,
        deps_factory=_deps_factory,
        extract_result=_extract_book_index_result,
        policy=book_index_policy,
        persistence=PersistencePolicy(on_complete=_persist),
    )


def build_book_retrieve_execution(
    artifact_api: ArtifactService,
    platform_client: PlatformClient,
) -> JobExecution:
    session = PlatformSession.connect(_PLATFORM_API_URL)
    embeddings = (
        EmbeddingsInterpreter(session, model=EMBEDDING_MODEL)
        if EmbeddingsInterpreter is not None else None
    )
    from mathai.math_book.vector_store import VectorStore

    vector_store = VectorStore()

    def _load_structure(book_id: str):
        """Load the newest `BookStructureArtifact` for `book_id` (nodes for
        source-traceability + edges for intent-gated graph expansion). Returns
        None if the book hasn't been indexed."""
        results = artifact_api.query(
            artifact_type="book_structure", fields={"book_id": book_id}, limit=1
        )
        return results[0] if results else None

    def _deps_factory(payload: dict) -> BookRetrieveDependencies:
        job_id = payload.get("_job_id")
        logger: WorkerLogger = WorkerLogger(job_id) if job_id else NullLogger()
        return BookRetrieveDependencies(
            book_id=payload.get("book_id", ""),
            query=payload.get("query", ""),
            k=int(payload.get("k", 8)),
            intent=payload.get("intent"),
            rerank=bool(payload.get("rerank", True)),
            embeddings=embeddings,
            vector_store=vector_store,
            load_structure=_load_structure,
            logger=logger,
        )

    def _persist(job_id: str, state: BookState) -> list[UUID]:
        """Mint the small `BookRetrievalArtifact` carrying the ranked hits so a
        retrieve run's answer is ref-resolvable like every other job's output."""
        if not state.book_id or not state.query:
            return []
        artifact = BookRetrievalArtifact(
            created_by_job=job_id,
            book_id=state.book_id,
            query=state.query,
            intent=state.intent,
            reranked=state.reranked,
            hits=[
                RetrievedHit(
                    chunk_id=h.chunk_id,
                    node_id=h.node_id,
                    label=h.label,
                    page=h.page,
                    heading_path=list(h.heading_path or []),
                    text=h.text,
                    score=h.score,
                )
                for h in state.hits
            ],
        )
        artifact_api.put(artifact)
        return [artifact.artifact_id]

    return JobExecution(
        name="book_retrieve",
        graph=book_retrieve_graph,
        state_type=BookState,
        start_node_key="Retrieve",
        node_registry=book_retrieve_node_registry,
        deps_factory=_deps_factory,
        extract_result=_extract_book_retrieve_result,
        policy=book_retrieve_policy,
        persistence=PersistencePolicy(on_complete=_persist),
    )


def register_execution(ctx: BootstrapContext) -> ExecutionDomain:
    return ExecutionDomain(
        name="math_book",
        job_executions=[
            build_book_index_execution(ctx.artifact_service, ctx.platform_client),
            build_book_retrieve_execution(ctx.artifact_service, ctx.platform_client),
        ],
        artifact_types=list(MATH_BOOK_ARTIFACTS.values()),
    )

"""math_book execution plane — index + retrieve graphs + persistence (SCAFFOLD).

Imports `pydantic_graph` (light) and, at *runtime* (inside the deps factories,
not at module load), the platform embeddings helper + the domain vector store —
so this module stays importable with only the graph engine present, matching
how `math_notes.execution` defers its media helpers. The worker imports this
after the catalog install pass.

The heavy pieces are stubs (#63 index / #64 retrieve): the graphs' node bodies
are TODO no-ops (see `workflow.py`), so `_persist` here only mints artifacts
from whatever end-state the stub nodes produced (empty in the scaffold). The
`EmbeddingsInterpreter` wiring is present as a documented seam but NOT invoked.
See `docs/book-rag-integration/DESIGN.md`.
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
    BookIndexArtifact,
    BookStructureArtifact,
)
from mathai.math_book.state import BookState
from mathai.math_book.workflow import (
    BookIndexDependencies,
    BookRetrieveDependencies,
    _extract_book_index_result,
    _extract_book_retrieve_result,
    book_index_graph,
    book_index_node_registry,
    book_retrieve_graph,
    book_retrieve_node_registry,
)

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
    # One session per worker process; PlatformSession's httpx client is lazy, so
    # building it at registration (before the API is necessarily reachable) is
    # safe — first use is at job run.
    session = PlatformSession.connect(_PLATFORM_API_URL)

    def _deps_factory(payload: dict) -> BookIndexDependencies:
        job_id = payload.get("_job_id")
        logger: WorkerLogger = WorkerLogger(job_id) if job_id else NullLogger()
        pr = payload.get("page_range")
        page_range = (int(pr["start"]), int(pr["end"])) if pr else None
        # TODO(#63): build the platform EmbeddingsInterpreter + the domain
        #   VectorStore here and pass them in — e.g.
        #     from ai_platform.ai.providers.embeddings import EmbeddingsInterpreter
        #     from mathai.math_book.vector_store import VectorStore
        #     embeddings = EmbeddingsInterpreter(session)
        #     vector_store = VectorStore()  # connects to the tenant DB (#63)
        #   Left None in the scaffold so nothing heavy is imported/invoked yet;
        #   the #61 platform helper isn't relied on at scaffold time.
        return BookIndexDependencies(
            pdf_ref=payload.get("pdf_ref", ""),
            book_id=payload.get("book_id", ""),
            page_range=page_range,
            embeddings=None,
            vector_store=None,
            logger=logger,
        )

    def _persist(job_id: str, state: BookState) -> list[UUID]:
        """Mint the skeleton + index-manifest artifacts from end-state.

        Scaffold: the stub nodes leave state empty, so this mints two shells
        (or nothing when there's no book_id). #63 fills state, so this persists
        the real skeleton + manifest with no signature change."""
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
            # chunks manifest is filled in #63 from state.chunk_ids.
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

    def _deps_factory(payload: dict) -> BookRetrieveDependencies:
        job_id = payload.get("_job_id")
        logger: WorkerLogger = WorkerLogger(job_id) if job_id else NullLogger()
        # TODO(#64): build EmbeddingsInterpreter + VectorStore (query embed +
        #   kNN) here, same seam as book_index above. Left None in the scaffold.
        return BookRetrieveDependencies(
            book_id=payload.get("book_id", ""),
            query=payload.get("query", ""),
            k=int(payload.get("k", 8)),
            intent=payload.get("intent"),
            embeddings=None,
            vector_store=None,
            logger=logger,
        )

    def _persist(job_id: str, state: BookState) -> list[UUID]:
        # TODO(#64): mint a small result artifact carrying the ranked hits so
        #   `book_retrieve` results are ref-resolvable like every other job.
        #   Scaffold: nothing to persist (stub Retrieve produces no hits).
        return []

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

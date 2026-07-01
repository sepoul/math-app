"""math_book control plane — the two `JobControl`s (schemas) + `register_control`.

Engine-free: imports models + artifacts only, never the graph engine
(`execution.py` / `workflow.py`). The API imports this at boot, and
`aiplatform declare-artifacts` imports it to publish the artifact-type contract
before the wheel/jobs exist — so it MUST stay import-safe with only
`aiplatform-core` installed (no pydantic_graph, no AI/vector deps).

Two jobs: `book_index` (PDF → skeleton + chunk/embed index) and `book_retrieve`
(query → hybrid, source-traceable hits). See `docs/book-rag-integration/DESIGN.md`.
"""
from __future__ import annotations

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.jobs.domain import BootstrapContext, ControlDomain
from ai_platform.jobs.execution_policy import JobControl
from ai_platform.jobs.result_fetcher import hydrate_artifact_refs
from mathai.math_book.artifacts import (
    MATH_BOOK_ARTIFACTS,
    BookIndexArtifact,
    BookStructureArtifact,
)
from mathai.math_book.models import (
    BookIndexResult,
    BookRetrievalResult,
    BookRetrieveInput,
    BookIndexInput,
)


def build_book_index_control(artifact_api: ArtifactService) -> JobControl:
    def _fetch_result(record) -> BookIndexResult:
        artifacts = hydrate_artifact_refs(record, artifact_api)
        structure = next(
            (a for a in artifacts if isinstance(a, BookStructureArtifact)), None
        )
        index = next((a for a in artifacts if isinstance(a, BookIndexArtifact)), None)
        return BookIndexResult(
            book_id=(structure.book_id if structure else (index.book_id if index else None)),
            node_count=(len(structure.nodes) if structure else 0),
            edge_count=(len(structure.edges) if structure else 0),
            chunk_count=(index.chunk_count if index else 0),
            structure=structure,
            index=index,
            # BaseJobResult.artifact_refs is list[UUID]; hydrated artifacts carry
            # UUID ids, so pass them through as-is.
            artifact_refs=[a.artifact_id for a in artifacts],
        )

    return JobControl(
        name="book_index",
        label="book_index",
        submit_input_type=BookIndexInput,
        result_type=BookIndexResult,
        gates=[],  # no human review
        fetch_result=_fetch_result,
    )


def build_book_retrieve_control(artifact_api: ArtifactService) -> JobControl:
    def _fetch_result(record) -> BookRetrievalResult:
        # Retrieval mints (at most) a small result artifact; the ranked hits are
        # rebuilt from end-state by `execution._extract_book_retrieve_result`.
        # This control-side fetch just surfaces the artifact refs for now — the
        # canonical hit payload lands in #64 alongside the retrieval logic.
        artifacts = hydrate_artifact_refs(record, artifact_api)
        return BookRetrievalResult(
            artifact_refs=[a.artifact_id for a in artifacts],
        )

    return JobControl(
        name="book_retrieve",
        label="book_retrieve",
        submit_input_type=BookRetrieveInput,
        result_type=BookRetrievalResult,
        gates=[],
        fetch_result=_fetch_result,
    )


def register_control(ctx: BootstrapContext) -> ControlDomain:
    return ControlDomain(
        name="math_book",
        job_controls=[
            build_book_index_control(ctx.artifact_service),
            build_book_retrieve_control(ctx.artifact_service),
        ],
        artifact_types=list(MATH_BOOK_ARTIFACTS.values()),
        runtime_selector="default",
        code_entrypoint="mathai.math_book.execution:register_execution",
        control_entrypoint="mathai.math_book.control:register_control",
    )

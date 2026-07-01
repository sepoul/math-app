# Book-RAG platform integration — design (distilled from recon)

Package the proven book-RAG spike as a **lean platform layer + a math-app domain**,
in platform language (jobs + artifacts), reusing the spike branch code.

## The split (boundary-correct per §13 + the PR-3 doc)

**Key recon finding:** the platform's `math-notes` PR-3 requirements doc
**explicitly forbids** a platform-owned vector store — *"vector store / semantic
search is NOT a platform requirement… embeddings never become a built-in; the
domain stands up its own pgvector table in the tenant storage plane and exposes a
retrieval tool."* So:

### Platform layer (`../ai-platform`) — ONE additive primitive
- **`ai_platform.ai.providers.embeddings`** — a generic `Embedder` provider
  helper, modeled EXACTLY on `providers/audio.py` (`AudioInterpreter`) and
  `providers/vision.py` (`ImageInterpreter`):
  - thin `embed_text(text, *, model="text-embedding-3-small", client=None) -> EmbeddingResult(vector, model, usage)`;
  - a class **`EmbeddingsInterpreter(media, *, model, client)`** (name matches the
    `AudioInterpreter`/`ImageInterpreter` family) with `embed(text)` +
    `embed_ref(storage_ref)`, duck-typed media source (PlatformSession/MediaService/FileRepository);
  - deferred `OpenAI()` (reads `OPENAI_API_KEY` at call time); no framework import at module load.
  - Lives in `packages/worker/src/ai_platform/ai/providers/embeddings.py`. Domains import `from ai_platform.ai.providers.embeddings import embed_text, EmbeddingsInterpreter`.
  - **Text-in / vector-out, domain-agnostic.** No corpus/RAG knowledge. This is the only platform change.
- **NO platform `VectorRepository`** (would violate the boundary). Vector storage is domain-owned.

### Domain layer (`math-app`) — the book-RAG domain, packaged as jobs + artifacts
Owns: the pgvector table (its own, in the tenant storage plane), chunking, hybrid
ranking, rerank (via `ai_platform.ai.providers.basic_agent` → Claude), and the
whole extraction→graph→retrieve pipeline. Reuses spike code:
- extraction (`spike/extraction-skeleton`), graph+refs (`spike/graph-grounding`),
  hybrid retrieval + rerank (`spike/hybrid-retrieval`), eval harness
  (`spike/eval-efficiency`).

Jobs (reuse the platform `jobs` concept — no local scripts / one-offs):
- **`book_index`** — PDF (storage_ref) → structured skeleton (nodes/edges) +
  chunk+embed (platform `Embedder`) into the domain pgvector table. Mints
  artifacts for the skeleton + graph.
- **`book_retrieve`** — query → hybrid retrieval (lexical + vector + type/label +
  intent-gated graph expansion) + optional Claude rerank → source-traceable hits.

Artifacts (`BaseArtifact` subclasses, registered in the domain `*_ARTIFACTS`):
- book skeleton node(s), graph edges, (and/or a compact index manifest).

## Reference conventions (from recon)
- Provider helpers live in the worker base; installed domain wheels import them at
  runtime (worker has both core+worker installed at boot).
- `basic_agent(model="claude-...", output_type=..., instructions=...) -> pydantic_ai.Agent` — the rerank/LLM path.
- Runtime: **default** (pydantic_graph + pydantic_ai + Logfire) — book-RAG has no crewai dep.

## Domain vector store (resolved)
The domain **owns its pgvector table in the tenant storage plane** (sanctioned by
the PR-3 doc). Lean v1: a small domain module `vector_store.py` connecting to the
tenant Postgres (connection available to the worker; reuse the spike's
`_shared/db.py` connect + pgvector pattern) with `upsert`/`knn_query` over a
domain-owned table (e.g. `math_book_chunks`, namespaced by `book_id`). No platform
`VectorRepository`. Keep it boring — the spike already proved this shape.

## Package + jobs (resolved)
- **New package `packages/math-book`** (`src/mathai/math_book/`), `runtime = default`.
- Files (mirror `packages/math-notes`): `control.py` · `execution.py` ·
  `workflow.py` · `state.py` · `models.py` · `artifacts.py` · `vector_store.py`
  · `pyproject.toml` · `bundle.toml`.
- **Jobs** (reuse the platform `jobs` concept — no local scripts):
  - `book_index`: `BookIndexInput(pdf_ref, book_id, page_range?)` → parse →
    extract structure (spike Track A) → build graph (spike Track B) → chunk +
    embed (platform `EmbeddingsInterpreter`) → persist to domain pgvector table →
    mint `BookStructureArtifact` + `BookIndexArtifact`. Result: `BookIndexResult`.
  - `book_retrieve`: `BookRetrieveInput(book_id, query, k, intent?)` → hybrid
    (lexical + vector + type/label + intent-gated graph expansion, spike Track C)
    + optional Claude rerank (`basic_agent`) → `BookRetrievalResult` (ranked,
    source-traceable hits). Mints a small result artifact.
- **Artifacts**: `BookStructureArtifact` (skeleton nodes + edges), `BookIndexArtifact`
  (chunk/index manifest), registered in `MATH_BOOK_ARTIFACTS`.
- **Rerank/LLM path**: `from ai_platform.ai.providers.basic_agent import basic_agent` (Claude).
- **Eval**: port the spike Track-D harness as a domain test that runs the deployed
  jobs over the shared slice and checks the numbers reproduce (right-place ~0.85,
  naive=0 on label/trace) — proves the packaging didn't regress the spike.

## Issue slate (epic + children)
- **E** [epic] Package book-RAG as platform-integrated jobs.
- **#P** [platform] add `EmbeddingsInterpreter` provider helper (+ test) — `../ai-platform`, additive, its own PR. *(base contract; wave 1)*
- **#S** [math-book] package scaffold: control/models/state/artifacts/bundle/pyproject (the domain contract). *(wave 1)*
- **#I** [math-book] `book_index` job — extraction + graph + chunk/embed + vector_store, reuse spike A/B + platform Embedder. *(needs #P, #S)*
- **#R** [math-book] `book_retrieve` job — hybrid + intent-gated graph + Claude rerank, reuse spike C. *(needs #S, #I)*
- **#V** [math-book] eval harness port + deploy + SDK regen + smoke (reproduce spike numbers on the deployed jobs). *(needs #I, #R)*

## Execution topology (token-aware)
- **P agent** (fresh, lean): the platform Embedder in `../ai-platform`.
- **D agent** (fresh, lean; reads this DESIGN + spike branches): builds #S, then
  **re-engaged via SendMessage** for #I → #R → (#V) so it inherits its OWN
  accumulated domain context across the coupled steps (cheap inheritance) instead
  of N cold agents re-reading. Forking the orchestrator's (large) context would
  itself burn tokens — session-continue is the economical inheritance here.
- Orchestrator reviews each PR, sequences merges, runs/【delegates】 deploy+verify.

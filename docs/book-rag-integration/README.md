# Book-RAG → platform integration — **COMPLETE** ✅

**Status: done, validated end-to-end on the deployed platform, nothing outstanding
that blocks the goal.** This is the packaging phase that turned the book-RAG
*spike* (#57, verdict GO) into real, platform-native jobs — no local scripts, no
one-off processes. Epic: **#59**.

## TL;DR (the close-out)

The proven book-RAG pipeline now runs as **platform jobs** over **platform
primitives**, split cleanly across the platform/math-app boundary, and a live
smoke reproduces the spike's headline finding. Every issue is closed, every PR
merged. One unrelated, pre-existing SDK build nit is tracked separately
(ai-platform#78) and does **not** affect the pipeline.

## What shipped

**Platform (`../ai-platform`) — one lean, additive primitive**
- `EmbeddingsInterpreter` (+ `embed_text`, `EmbeddingResult`) in
  `packages/worker/src/ai_platform/ai/providers/embeddings.py` — a generic
  `text → vector` provider helper modeled exactly on `AudioInterpreter` /
  `ImageInterpreter` (deferred OpenAI client, duck-typed media source, 12 tests).
  **No platform vector store** — that stays domain-owned, per §13 + the PR-3 doc.
  → **ai-platform#77 (merged).**

**Domain (`packages/math-book`, new) — the book-RAG pipeline as jobs + artifacts**
- Jobs: **`book_index`** (pdf_ref → extraction + graph → chunk + embed → the
  domain's own `math_book_chunks` pgvector table + artifacts) and
  **`book_retrieve`** (query → hybrid lexical+vector+type/label + intent-gated
  graph expansion + Claude rerank → source-traceable hits).
- Artifacts: `book_structure`, `book_index`, `book_retrieval`.
- Reuses the spike branch code (extraction ← Track A, graph ← Track B, retrieval
  `C_full` ← Track C), calling the platform `EmbeddingsInterpreter` + `basic_agent`.
  → **math-app#65 (merged).** Eval harness + deploy proof → **math-app#66 (merged).**

## The verdict — validated on the deployed jobs

Live smoke: Tu PDF via `POST /media` → `book_index` the shared slice →
**270 nodes / 1917 edges / 268 chunks** → `book_retrieve` all 26 gold queries.

| metric | deployed (page-aware) | spike (frozen) | naive view |
|---|---|---|---|
| recall@5 | **0.808** | 0.854 | (same page hits) |
| MRR | **0.830** | 0.910 | 0.54 |
| exact-label-hit | 0.462 | 0.500 | **0.000** |
| traceability | **1.000** | 0.988 | **0.000** |

**The spike's core result reproduced on the packaged pipeline:** structure wins,
and the naive view collapses to **0** on label-hit + traceability (it finds a
page but can't name or ground the unit). The small gap vs the frozen spike is
explained and non-regression: a broader slice (270 vs 143 nodes → more
distractors) and strict-join on pre-freeze gold node_ids (the spike's own R4
caveat). Full detail: `packages/math-book/eval/RESULTS.md`.

## How it was run (the orchestration)

Control-plane + agents, but **token-disciplined** this time (the explicit ask):

- **Recon once, compact.** Two read-only `Explore` scouts returned briefs
  (~120K tokens total) instead of every implementer re-exploring the repos.
- **Fresh + bounded implementers, session-continue for coupled work.** The
  domain package was built by **one agent** re-engaged across scaffold → index →
  retrieve via `SendMessage`, so it inherited **its own** accumulated context
  (stable contracts across steps) rather than forking the orchestrator's large
  context — forking that would have been the token-explosion to avoid.
- **The full agent tree + per-node token accounting** live in
  [`agent-topology.json`](agent-topology.json). Whole integration ≈ **948K**
  subagent tokens.

```
orchestrator (control plane)
├─ scout: platform primitives            (Explore, done)
├─ scout: domain packaging               (Explore, done)
├─ impl: platform EmbeddingsInterpreter  (#61 → ai-platform#77, merged)
├─ impl: math-book domain                (#60→#63→#64, session-continue → math-app#65, merged)
│    └─ resume ×2 (scaffold → book_index → book_retrieve)
└─ impl: eval + deploy + smoke           (#62 → math-app#66, merged)
```

## Ledger

| item | state |
|---|---|
| Epic #59 | closed by this PR |
| #60 scaffold · #61 embedder · #62 eval/deploy · #63 index · #64 retrieve | **all closed** |
| ai-platform#77 · math-app#65 · math-app#66 | **all merged** |
| ai-platform#78 (SDK `tsc` naming drift) | open — **pre-existing, out of scope**, does not affect the pipeline |

## For whoever builds the Mentor Loop (#50) next

- Ground `book_retrieve` for #55 (book skeleton): it returns named,
  page-traceable units (`node_id + label + page + heading_path`) — exactly what
  "redo Problem 2.16, here" needs.
- #53 (bridge canonicalization): the deterministic + *author-stated* `depends_on`
  edges are in; the **conceptual term-overlap bridges remain #53's open hard
  problem** and want their own spike (as the original spike concluded).
- Design + decisions: [`DESIGN.md`](DESIGN.md). Spike provenance: #57 +
  `spikes/book-rag/REPORT.md`.

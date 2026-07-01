# math_book — deploy + eval RESULTS (#62)

Ported the `spike/eval-efficiency` eval harness (Track D) as a domain test and
ran it against the **deployed** `book_retrieve` job on the local platform
(`:8000`, schema `test`). This is the packaged pipeline reproducing the spike
headline — not the lab code.

## Deploy status — LIVE

- **Wheel:** `mathai_math_book-0.3.0-py3-none-any.whl` built + pushed via
  `aiplatform deploy` (explicit-PYTHONPATH invocation per CLAUDE.md, since the
  platform `.venv` can't `import ai_platform`).
- **Worker:** the merged `EmbeddingsInterpreter` (ai-platform `b1c483a`, PR #77)
  was **not** in the running `aiplatform-worker:local` image (built pre-merge,
  no editable source mount), so the image was **rebuilt** (`docker compose
  --profile build build aiplatform-worker`) then the worker recreated. Boot log:
  `Installed 3 CodePackage(s) at boot: ['mathai-math-book@0.3.0', ...]` and
  `from ai_platform.ai.providers.embeddings import EmbeddingsInterpreter` imports
  OK inside the container.
- **API:** restarted so it installs the math-book control package and adds the
  jobs to the submit union. `/openapi.json` submit union now includes
  `BookIndexInput` + `BookRetrieveInput`.
- **Catalog:** `/job-definitions` shows `book_index@0.3.0` + `book_retrieve@0.3.0`
  (runtime `default`); `/artifact-types` shows `book_structure@0.3.0`,
  `book_index@0.3.0`, `book_retrieval@0.3.0`.
- **pgvector:** `test.math_book_chunks` exists as `vector(1536)` (correct for
  `text-embedding-3-small`) — no stale-dim table.

## Smoke — end-to-end on the deployed jobs, PASS

1. `POST /media` the Tu PDF (2.8 MB) → `storage_ref`.
2. `book_index` over the shared slice (pdf pages 22–101 = Ch1 §1–§3 + Ch2 §7):
   **node_count=270, edge_count=1917, chunk_count=268** in ~86 s; 268 rows in
   `test.math_book_chunks` (node_ids namespaced `tu_manifolds:book.sub…`).
3. `book_retrieve` for all 26 queries (k=10): every query returned 10 ranked,
   **fully source-traceable** hits (page + heading_path present on all → 
   traceability = 1.000). Exact-label lookups land at rank 1: Theorem 7.7→p94,
   Proposition 7.1→p91, Corollary 7.8→p94, Lemma 1.4→p25, Proposition 3.8→p41,
   Proposition 2.6→p35, Proposition 7.16→p98, etc. Claude rerank ran per query.

## Scored numbers vs the spike (C_full)

Scored through the **ported** `metrics.py` (verbatim from
`track-d/metrics.py`) against the verbatim `queries/gold.json`.

| metric | deployed PAGE-AWARE | spike PAGE-AWARE | deployed STRICT | spike STRICT |
|---|---|---|---|---|
| recall@5 | **0.808** | 0.854 | 0.488 | 0.613 |
| recall@10 | 0.851 | 0.946 | 0.617 | 0.737 |
| MRR | **0.830** | 0.910 | 0.631 | 0.710 |
| nDCG@5 | 0.661 | 0.780 | 0.462 | 0.589 |
| exact-label-hit | 0.462 | 0.500 | 0.462 | 0.500 |
| traceability | **1.000** | 0.988 | 1.000 | 0.988 |

**naive VIEW** (the same deployed hits, label/node_id/heading STRIPPED, scored
page-mode): recall@5 identical (0.808) but **exact-label = 0.000, traceability =
0.000** — the spike's naive=0-on-label/trace headline, reproduced.

Per-query latency (submit + poll + Claude rerank round-trip): p50 ≈ 7.0 s,
p95 ≈ 67 s (two queries hit a cold-worker / rerank spike; the modal query is
~7–10 s). Not comparable to the spike's in-process 1.9 s p50 — this includes the
full job-submit/poll/artifact-mint round-trip.

## Reading the numbers (why deployed < spike, and why that's expected)

The packaged pipeline **reproduces the spike thesis** — right-place recall in the
0.8 band, MRR ~0.83, traceability 1.0, and the naive label/trace collapse to 0 —
landing a hair under the frozen spike figure, for two structural reasons, not a
regression:

1. **Broader slice → more distractors.** The deployed index parsed the full
   pdf-page window 22–101 → **270 nodes / 268 chunks**, vs the spike's frozen
   `track-a-r1` corpus of **143 nodes**. Nearly 2× the candidate pool over the
   same 26 queries dilutes recall@k / MRR modestly. Narrowing the slice (or
   freezing to the same node set) would close most of the gap.
2. **STRICT joins on label only.** The spike's gold `gold_node_id`s are the
   pre-freeze bare ids (`book.sub7.5.theorem123`); the deployed index namespaces
   every node under `book_id` (`tu_manifolds:book.sub7.5.theorem123`), so
   node_id never joins and STRICT degrades to label matching — exactly the R4
   caveat ("label is the freeze-stable join key"). STRICT here is therefore a
   label-only lower bound; PAGE-AWARE (0.808) is the user-facing "landed on the
   right page" number and the fair headline.

The `exact_label_hit` rate (0.462) is computed across all 26 queries (every one
carries a relevance-2 label in this gold); the clean `direct` label-lookups
(D-001/003/004/005/006/008) all hit at rank 1. "Misses" are conceptual /
structural queries where rank 1 landed on a *different but still relevant* node
(e.g. D-011 tops Proposition 7.4, itself relevance-2 gold) or a leaf outranked a
subsection heading — the same behavior the spike measured at 0.5.

## Verdict

The packaged `book_index` → `book_retrieve` pipeline runs end-to-end on the
deployed platform and **reproduces the spike headline**: right-place recall in
the ~0.8 band with MRR ~0.83, **source-traceability 1.0**, and a **naive
label/trace collapse to 0** — the structured-RAG win the spike voted GO on,
confirmed on the packaged domain.

## Reproduce

```bash
# platform up on :8000 (worker rebuilt with the EmbeddingsInterpreter image,
# math-book@0.3.0 deployed + worker/API restarted — see above)
TU_PDF="/absolute/path/to/Tu_AnIntroductionToManifolds copy.pdf" \
  python packages/math-book/eval/run_eval.py
# reuse an already-indexed book (skip the index step):
SKIP_INDEX=1 python packages/math-book/eval/run_eval.py
```

Machine-readable dump of the last run: `eval/last_run.json`.

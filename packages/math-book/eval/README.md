# packages/math-book/eval/ — the deployed-retrieval eval harness (#62)

The measuring stick for `book_retrieve`, ported from the book-RAG spike
(`spike/eval-efficiency`, Track D) and pointed at the **deployed** job on a live
platform — not the lab code.

## Files

- `metrics.py` — the retrieval metrics (recall@k, MRR, nDCG@k, exact-label-hit,
  source-traceability + `score_run`). **Verbatim** from
  `spike/eval-efficiency:spikes/book-rag/track-d/metrics.py` (the one seam the
  spike policed — don't invent new metrics; import these). Pure-python, no DB.
- `queries/queries.json`, `queries/gold.json` — the 26-query set + 66 graded
  gold rows over the shared slice (Tu Ch1 §1–§3 + Ch2 §7 Quotients). **Verbatim**
  from `spike/eval-efficiency:spikes/book-rag/queries/`. The measuring stick;
  gold is anchored to stable Tu labels + pdf pages.
- `run_eval.py` — the deploy-smoke + scorer. Uploads the Tu PDF → `book_index`
  the slice → `book_retrieve` every query over the DEPLOYED job (HTTP, stdlib
  only — no SDK/domain import) → scores via `metrics.py`, PAGE-AWARE (right
  place) + STRICT (right unit), plus a naive VIEW (same hits, label/heading
  stripped) that reproduces the spike's naive=0-on-label/trace collapse.
- `last_run.json` — machine-readable dump of the most recent run.
- `RESULTS.md` — the recorded run + numbers vs the spike + the verdict.

## Run

```bash
TU_PDF="/absolute/path/to/Tu_AnIntroductionToManifolds copy.pdf" \
  python packages/math-book/eval/run_eval.py     # full: index + retrieve + score
SKIP_INDEX=1 python packages/math-book/eval/run_eval.py   # reuse indexed book
```

Env: `API_URL` (default `http://localhost:8000`), `BOOK_ID` (`tu_manifolds`),
`SLICE_START`/`SLICE_END` (pdf pages, default 22..101), `K` (default 10).

# Track D — Eval harness, "is it efficient?", speed & cost — FINDINGS

Scope/contract: issue **#57** (Track D). Leads on **speed/cost + the verdict**.
Owns the **measuring stick**, not a retriever. Tables: `d_*`. Bucket: `track-d/`.
Publishes `d_queries`/`d_gold` **early** (also mirrored to `../queries/`) so
Track C can score against them.

**Question:** what does "efficient on my book" mean, measurably — and what's
the go/no-go?

> Ship the query set first; it unblocks C.

## Query suite (grounded in Tu)
- direct lookups (by label/definition): …
- conceptual lookups: …
- structural lookups (before/after, what's-in-this-section): …
- graph-expansion lookups: …

## Metrics + gold
- metrics: recall@k, MRR, exact-label hit-rate, source-traceability …
- gold labelling method: …

## §17 failure-attribution decision tree
- when retrieval is wrong, is it: heading segmentation / reading order /
  theorem-proof boundary / page mapping / lexical / vector / metadata /
  rerank / graph expansion? …

## Speed/cost ledger (end-to-end slice)
| stage | metric | value |
|---|---|---|
| extraction | seconds | |
| index build | seconds | |
| query | latency_ms | |
| query | tokens / usd | |

## Go / no-go recommendation (control plane completes in SYNTHESIS.md)

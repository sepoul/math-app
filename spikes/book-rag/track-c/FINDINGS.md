# Track C — Indexing & hybrid-retrieval bake-off — FINDINGS

Scope/contract: issue **#57** (Track C). Leads on **the headline result**.
Tables: `c_chunks`, `c_baseline_chunks` (embedding dim is your choice — bare
`vector` column; brute-force KNN is fine at slice scale, add an HNSW index only
if you fix a dim). Consumes `a_*`/`b_*` (or seed) **and Track D's `d_queries`/
`d_gold`**. Bucket: `track-c/`.

**Question (the headline):** does coarse-to-fine, structure-aware hybrid
retrieval (lexical FTS + pgvector + metadata/type boosts + rerank) **beat a
naive fixed-window chunk-embedding baseline** on Tu's queries — and which
signals carry the weight?

> Do NOT invent your own metrics — score against Track D's query set/gold.

## The two systems
- Structured-hybrid: signals = …
- Naive baseline: fixed-window size = …, embedder = …

## Head-to-head (on D's query set)
| approach | recall@5 | MRR | exact-label hit | source-traceable |
|---|---|---|---|---|
| naive baseline | | | | |
| structured-hybrid | | | | |

## Ablation (which signal carries the weight)
| signal removed | Δ recall@5 | Δ MRR |
|---|---|---|

## Speed / cost
- Index build time; per-query latency; tokens/$ per query: …

## Recommendation (1 paragraph)

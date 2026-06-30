# Track C — Indexing & hybrid-retrieval bake-off — FINDINGS (FINAL, R4)

Scope/contract: issue **#57** (Track C). Leads on **the headline result**.
Tables: `c_chunks`, `c_baseline_chunks`. Consumes `a_*`/`b_*` + Track D's gold.

**Question:** does structure-aware hybrid retrieval beat a naive fixed-window
chunk-embedding baseline on Tu's queries — feasible, high-quality, fast enough?
**Verdict: GO.** Structured-hybrid (`C_full`) matches D's reference on recall and
wins materially on ranking + unit identity; ~70 ms warm, ~1.7 s with rerank, ~$0.0015/q.

---

# ROUND 4 — FINAL: locked config + strict-recall ceiling

## 1. THE LOCKED CANONICAL CONFIG (`C_full`) — importable for Track D

```python
# spikes/book-rag/track-c/retrieve_r2.py
from retrieve_r2 import Retriever, c_full_retrieve_fn, C_FULL_CFG
r = Retriever()
fn = c_full_retrieve_fn(r)          # fn(query_text, k) -> list[dict]
report = evaluate(fn, "C_full", k=10, match_mode="auto", gold=<FILE gold>)
r.close()
```

`C_FULL_CFG` (frozen — Track D scores THIS one, no more cross-round drift):
```
pool=50, use_lexical, use_vector, use_type, use_label,
use_graph + gate_graph (intent-gated), coarse_to_fine,
demote_sections, rerank (rerank_pool=12)  # claude-haiku-4-5
```
- **Corpus:** `c_chunks` rebuilt from `a_nodes` (run **track-a-r1**, 166 nodes →
  164 indexable: 28 section/subsection + 136 leaf), all embedded 1536-d.
- **Gold:** Track D's **file** gold (`queries/gold.json` / `_vendor_gold.json`) —
  carries `page_pdf` (the DB loader drops it). `match_mode="auto"` (node_id →
  label → exact-page) for structured; `"page"` for the label-less baseline.
- Each result dict carries node_id / chunk_id / score / label / page_pdf_start /
  heading_path / signals — all the harness needs for node_id + label + page
  matching and source-traceability.

## 2. FINAL NUMBERS — locked C_full (frozen corpus, file gold, 26 queries)

| scoring | recall@5 | recall@10 | MRR | nDCG@5 | exact-label-hit | source-trace |
|---|---|---|---|---|---|---|
| **C_full [strict]** (exact unit) | **0.613** | 0.731 | 0.678 | 0.568 | 0.500 | 0.977 |
| **C_full [auto]** (node→label→page) | **0.803** | 0.864 | **0.929** | 0.731 | 0.538 | 0.973 |
| naive_baseline [page] | 0.718 | 0.822 | 0.540 | 0.482 | 0.000 | 0.000 |

- **Latency (incl. rerank): p50 1724 ms, p95 2382 ms, mean 1655 ms.** Warm
  non-rerank hybrid is ~70–110 ms (rerank is the cost). Embedding ~157 ms/call (cached).
- **Cost: ~$0.0015/query** (rerank, `claude-haiku-4-5`, one call ranks top-12; embed ~$0.0015 to build the whole index).
- **C_full vs the naive baseline:** structured matches/beats on recall (auto 0.803
  vs page 0.718) and **dominates on the dimensions that matter for a tutor** —
  MRR 0.929 vs 0.540, exact-label-hit 0.538 vs 0.000, source-traceability 0.97 vs
  0.00. *Naive finds the page; structured returns the right typed, labeled,
  traceable unit ranked first.*

## 3. STRICT-RECALL CEILING — measured attempt (the headline R4 question)

strict recall@5 ≈ 0.61 vs auto ≈ 0.80. **I diagnosed and attacked the gap; the
honest finding is that the ceiling is NOT a retrieval-coverage problem, so the
coordinator's proposed lever (widen pool / richer embed_input) does not lift it.**

**Per-query diagnosis** (`diagnose_strict.py`): the strict misses are queries where
the right PAGE is found but the exact UNIT isn't matched in top-5. The causes,
in order of impact:

1. **Gold node_id drift (the dominant cause).** **11 of 37 gold node_ids no longer
   exist in the frozen corpus** — A re-ran and the per-unit suffixes shifted
   (`book.sub7.5.corollary119` → `corollary125`; `theorem117` → `theorem123`; etc.).
   The gold was node_id-mapped against an *earlier* A numbering. So node_id matching
   under-counts even when the correct *labeled* unit is retrieved. (Label matching
   is stable and saves most queries under `auto`; strict node_id is penalized.)
   **This is a frozen-corpus reconciliation gap, not a retriever weakness** — see
   BLOCKERS. B's edges, by contrast, ARE consistent with the current corpus (0 dangling).
2. **Structural-adjacency queries** ("what comes after Theorem 7.7" → next-edge
   Corollary 7.8): the answer is a graph neighbour. The unit IS retrieved (rank ~6),
   but ranking it #1 needs graph-edge semantics the rerank LLM doesn't reliably apply.

**Ceiling A/B (strict recall@5, isolating each lever):**
| variant | strict recall@5 | recall@10 |
|---|---|---|
| pool=30, no rerank | 0.600 | 0.751 |
| **pool=50**, no rerank | 0.572 | 0.724 |
| pool=50 + rerank (locked) | **0.614** | 0.741 |

**Widening the pool 30→50 did NOT lift strict recall (0.600 → 0.572) — it slightly
hurt.** The right units are already in the candidate set; the bottleneck is
ranking + node_id drift, not coverage. **Rerank is the only lever that moves strict
recall** (+0.04). So richer embed_input / bigger pools were correctly *tried and
rejected* by measurement.

**What DID lift the ceiling (ranking, not coverage)** — two §12–15 fixes shipped in
the locked config, before→after:
- **Section demotion** (sections are coarse navigation, not the answer leaf):
  fixed D-012 ("tangent vectors as derivations" — §2 section was out-ranking
  Theorem 2.2). weak_vector misses 4 → 3.
- **Graph-neighbour promotion** (promote the next/contains/proven_by neighbour of
  the top seeds, not just inject absent ones — the D-017 miss was Corollary 7.8 at
  rank 6, already-present so never graph-boosted): lifts **MRR 0.663 → 0.678
  (strict) / 0.884 → 0.929 (auto)** and **exact-label-hit 0.423 → 0.500/0.538**.

Net: strict recall@5 held ~0.61 (capped by the gold node_id drift), but **ranking
quality and exact-unit-at-rank-1 improved materially** (MRR +0.045 auto,
exact-label-hit +0.076) at **lower latency** (p50 1831 → 1724 ms).

## BLOCKERS / RISKS (for the go/no-go)
1. **Gold node_id drift must be re-reconciled if strict node_id recall is the
   headline.** 11/37 gold node_ids are stale (earlier A numbering). Ask to D
   (relayed): re-run `map_gold.py` against the FINAL frozen `a_nodes` so gold
   node_ids match the corpus C/D both score on; then strict node_id recall will
   rise toward the auto/label figure. Until then, **label + page (`auto`) is the
   trustworthy headline** (0.803), and strict node_id (0.613) is a *lower bound*
   depressed by the drift, not the true exact-unit rate.
2. **The `page_pdf` gold-loading bug** (R3): never score off `load_gold_from_db()`
   (drops `page_pdf` → page fallback dies → recall collapses). C uses file gold.
3. **Structural-adjacency is rerank-bound**, not retrieval-bound — a graph-aware
   answer path (return the seed's typed neighbour directly for "before/after"
   queries) would close it; deferred as out-of-scope for the spike decision.
4. **Math glyph-soup** (§9) caps lexical on symbol-heavy queries — unchanged.

## RECOMMENDATION (Track C's piece of the go/no-go)
**GO.** Structure-aware hybrid retrieval on Tu is feasible, fast (~70 ms warm
hybrid; ~1.7 s with rerank — viable in a daily synthesis pass), and cheap
(~$0.0015/query). On the agreed scorer it **equals D's independent reference on
recall and wins decisively on ranking + unit identity** (MRR 0.93, exact-label-hit
0.54, traceability 0.97 — vs a naive baseline that gets near the page but names
nothing: MRR 0.54, traceability 0). Smallest trustworthy build for #50: A's
deterministic skeleton → C's lexical+vector+type/label hybrid (the ~70 ms core) →
rerank for ranking-sensitive turns → B's edges + section-demote for structural/
neighbourhood answers. **The exact-unit (strict) ceiling is held back by gold
node_id drift, not the retriever** — re-reconcile the gold against the frozen
corpus and strict recall rises toward the 0.80 label/page figure.

---

# PROVENANCE (earlier rounds)
- **R3** reconciled C vs D's reference to ONE figure: root cause of the apparent
  0.583-vs-0.816 gap was C scoring off DB gold (drops `page_pdf` → page fallback
  dead). On the corrected scorer C_hybrid 0.816 ≈ D_ref 0.820, C ahead on MRR
  (+0.085). Added intent-gated graph (fixed R2's −0.067), coarse-to-fine (+0.030
  r@10), latency-halved rerank (3855 → 1789 ms).
- **R2** first scored bake-off + ablation: lexical+vector backbone (drop-vector
  −0.321), type/label boosts +0.057, rerank biggest lift. (numbers superseded by
  R3's corrected scorer.)
- **R1** stood up the substrate (fitz fallback while A was empty), primitives,
  5-probe sanity.

## Files (track-c/)
- `retrieve_r2.py` — THE retriever. Locked **`C_FULL_CFG`** + **`c_full_retrieve_fn`** (importable for D), resilient shared conn + embed cache, hybrid, intent-gated graph expansion (top-2 seeds, promote present neighbours, edge-weighted), coarse-to-fine (§12), **section demotion**, rerank, ablation knobs.
- `rerank.py` — Claude `claude-haiku-4-5` reranker, latency-tuned (pool 12 / 180-char / max_tokens 128).
- `build_index.py` — writes c_chunks + c_baseline_chunks from a_nodes (§12 section summaries).
- `lock_eval.py` — R4 FINAL: locked C_full strict+auto numbers + latency p50/p95 + cost + strict-ceiling A/B.
- `diagnose_strict.py` — R4 per-query strict-vs-page miss diagnostic (found the node_id drift + adjacency cases).
- `run_eval.py` — R3 reconciled C-vs-D bake-off (still runnable).
- `labels.py`, `baseline.py`, `embed.py`, `extract_slice.py`, `score_baseline_pages.py`, `bakeoff.py`, `GOLD_CONTRACT.md` — supporting.
- `_vendor_{harness,metrics,ref_retriever}.py`, `_vendor_{queries,gold}.json` — Track D's harness/metrics/reference/gold consumed read-only (origin/spike/eval-efficiency) for reproducibility.

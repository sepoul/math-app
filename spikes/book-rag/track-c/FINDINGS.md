# Track C — Indexing & hybrid-retrieval bake-off — FINDINGS

Scope/contract: issue **#57** (Track C). Leads on **the headline result**.
Tables: `c_chunks`, `c_baseline_chunks`. Consumes `a_*`/`b_*` + Track D's
`d_queries`/`d_gold`. Bucket: `track-c/`.

**Question (the headline):** does structure-aware hybrid retrieval (lexical FTS +
pgvector + metadata/type boosts + rerank) **beat a naive fixed-window
chunk-embedding baseline** on Tu's queries — and which signals carry the weight?

---

# ROUND 3 — RECONCILED to ONE agreed number + retrieval depth. VERDICT: structured wins; C ≈ D's reference; gap was a measurement artifact.

R3 priority was resolving the R2 discrepancy (C's hybrid 0.583 vs D's reference
0.816 on "the same" gold). **Resolved.** Then deepened retrieval (intent-gated
graph, coarse-to-fine, latency-tuned rerank) on **A's frozen corpus** (159
a_nodes; C rebuilt `c_chunks` → 157 indexable units), scored on **D's CURRENT
harness/metrics**, `match_mode="auto"` (node_id → label → page fallback).

## THE RECONCILED BAKE-OFF (D's harness, match_mode=auto, frozen corpus, 26 q)

| run | recall@5 | recall@10 | MRR | nDCG@5 | exact-label-hit | source-trace | p50 ms |
|---|---|---|---|---|---|---|---|
| naive_baseline¹ | 0.718 | 0.822 | 0.540 | 0.482 | 0.000 | 0.000 | 197 |
| D_ref_hybrid | 0.820 | 0.908 | 0.777 | 0.687 | 0.423 | 0.977 | 1113 |
| **C_hybrid** | **0.816** | **0.924** | **0.862** | **0.716** | 0.423 | 0.981 | **73** |
| C_hybrid+graph_gated | 0.808 | 0.901 | 0.862 | 0.711 | 0.423 | 0.981 | 76 |
| C_hybrid+coarse_to_fine | 0.816 | **0.954** | 0.856 | 0.698 | 0.423 | 0.988 | 109 |
| C_hybrid+rerank | **0.864** | 0.939 | 0.856 | 0.748 | 0.423 | 0.981 | 1789 |
| **C_full** (graph+cf+rerank) | 0.854 | 0.946 | **0.910** | **0.780** | **0.500** | 0.988 | 1938 |

¹ label-less baseline scored under the agreed honest secondary `match_mode="page"`
(exact pdf page == gold page); all structured runs use `auto`. All six C/naive
runs persisted to `d_results` + `d_speed_cost`.

## WHAT RESOLVED THE DISCREPANCY (the headline of R3)

**It was a measurement-state artifact, not a retrieval-quality gap. C's retriever
and D's reference agree to within noise on the identical scorer + corpus:**

| metric | C_hybrid | D_ref_hybrid | Δ(C−D) |
|---|---|---|---|
| recall@5 | 0.816 | 0.820 | −0.004 |
| recall@10 | 0.924 | 0.908 | +0.015 |
| MRR | 0.862 | 0.777 | **+0.085** |
| nDCG@5 | 0.716 | 0.687 | +0.029 |

Two things drove the apparent R2 gap, both now fixed/aligned:
1. **A `page_pdf` gold-loading bug in C's eval wiring (the big one).** D's harness
   `load_gold_from_db()` reads node_id/label/relevance but **silently drops
   `page_pdf`** (the column exists in `d_gold` but isn't selected). In R2 C scored
   off that DB gold, so `GoldItem.page_pdf` was always `None` and the `auto`
   matcher's **page fallback could never fire** — every page-locatable answer
   without an exact node_id/label hit scored 0. D's own runs used the **file**
   gold (`load_gold`, which *does* carry `page_pdf`). Switching C to
   `harness.load_gold(_vendor_gold.json)` restored the page fallback and C jumped
   0.564 → **0.816**, matching D. (node_ids/labels are identical between the file
   and DB gold, so structured node_id matches are unchanged — only the page-fallback
   credit was being lost.)
2. **Corpus/gold were a moving target.** A grew 143 → **159** nodes (closed the 6
   recall gaps + added bold-inline `def:` nodes); gold node_ids were resolved to
   A's ids by D's `map_gold.py`; D's metrics gained `match_mode`. C re-indexed off
   the frozen 159-node corpus this round so both tracks measure the same thing.

**Agreed match rule (with D):** `node_id` rigorous → `label` → **page (exact)**
fallback for label-less systems = `match_mode="auto"` for structured, `"page"` for
the naive baseline. C adopted D's harness/metrics verbatim (vendored read-only).
**One agreed figure: structured hybrid recall@5 ≈ 0.82, MRR ≈ 0.86, lifting to
recall@5 0.86 / MRR 0.91 with the depth additions.** C is the recommended system
(same recall as D's reference, materially better ranking: MRR +0.085).

## Is the baseline useless? No — the honest nuance holds

naive_baseline (page±exact): **recall@5 0.718** — a fixed window lands on the right
page often (dense slice). But MRR 0.540 vs structured 0.86–0.91, and **exact-label-
hit 0.000 / source-traceability 0.000**: it cannot name the unit ("Theorem 7.7"),
return the proof, or give a hierarchy path. *Naive finds the page; structure
returns the right typed unit, ranked first, traceable.* (Spec §17: for math books
segmentation/structure matters more than the embedder — borne out.)

## RETRIEVAL DEPTH (Δ vs C_hybrid)

| addition | Δrecall@5 | Δrecall@10 | ΔMRR | ΔnDCG@5 | note |
|---|---|---|---|---|---|
| +graph_gated | −0.008 | −0.023 | +0.000 | −0.006 | **neutral** (R2 was −0.067; intent gate fixed the regression) |
| +coarse_to_fine | +0.000 | **+0.030** | −0.006 | −0.018 | helps recall@10 (fetches the right section's leaves, §12) |
| +rerank | **+0.048** | +0.015 | −0.006 | **+0.031** | biggest single lift; latency-tuned |
| **+full** (all) | +0.038 | +0.022 | **+0.048** | **+0.063** | best ranking overall (MRR 0.910, nDCG 0.780, exact-label 0.500) |

1. **Intent-gated graph expansion (R3 fix):** only fires for structural/graph-
   expansion intent (regex gate, `is_structural_intent`), walks B's edges incl the
   now-live `references`/`referenced_by` (37+37) + contains/next/proven_by, scored
   strictly below seeds. Net **neutral on aggregate (−0.008)** — it no longer hurts
   (R2's global injection was −0.067). In C_full it lifts **MRR to 1.00 on
   structural and graph_expansion** categories (puts the seed theorem + its
   proof/corollary/refs at the very top). It does not raise recall@5 because the
   right *primary* answer was already retrieved by hybrid; expansion improves the
   neighborhood/ordering, which is what those query types actually want.
2. **Coarse-to-fine (§12, now exploited):** retrieve top-3 section nodes by
   vector, boost leaves whose enclosing section is in that set. **+0.030 recall@10**
   — pulls the right section's leaves into the window. Surfaces A's bold-inline
   `def: quotient topology`/`def: quotient space` nodes for "definition of the
   quotient topology" (A's gap-closing landed).
3. **Rerank — kept (biggest lift), latency attacked:** pool 20→**12**, snippets
   300→**180 chars**, `max_tokens` 512→**128**. **p50 latency 3855 ms → 1789 ms
   (−54%)**, cost **~$0.00352 → ~$0.00144/query**, with the recall/nDCG lift intact.

## BY CATEGORY recall@5 | MRR (C_hybrid → C_full)
| category | C_hybrid | C_full |
|---|---|---|
| direct | 0.94 / 0.94 | 0.94 / 0.94 |
| conceptual | 0.71 / 0.77 | **0.83** / 0.77 |
| structural | 0.90 / 0.88 | 0.90 / **1.00** |
| graph_expansion | 0.66 / 0.88 | 0.66 / **1.00** |

The page-fallback (now working) lifts structural from R2's 0.31 → 0.90 — most
structural answers *are* page-locatable; the R2 0.31 was the same `page_pdf`
loading bug. Graph expansion + rerank push graph_expansion/structural MRR to 1.00.

## SPEED / COST (warm, single resilient connection)
- Warm hybrid **~73 ms p50**; +coarse_to_fine ~109 ms (one extra section query);
  +graph ~76 ms. Query embedding ~175 ms (cached per query text).
- **Rerank: p50 1789 ms** (was 3855 ms in R2 — pool/snippet/max_tokens tuning),
  **~$0.00144/query** (`claude-haiku-4-5`, one call ranks the top-12).
- Index build (`build_index.py --source a_nodes`, 157 units): ~12 s, ~$0.0015 embed.
- Latency, not cost, remains the rerank constraint — but ~1.8 s is now viable
  inside a daily synthesis pass; the non-rerank hybrid is ~70 ms.

## BLOCKERS / RISKS
1. **The `page_pdf` gold-loading bug must not regress** — anyone scoring off
   `load_gold_from_db()` re-introduces the R2 artifact (page fallback dead → recall
   collapses). Ask to D (relayed): have `load_gold_from_db` also SELECT `page_pdf`,
   or document that file-gold is the scoring source. C uses file-gold.
2. **Graph expansion lifts ranking, not recall** — it improves neighborhood/MRR for
   structural queries but doesn't add new primary hits. That's the right behavior
   for §14, but means structural recall is bounded by what hybrid already finds.
3. **nDCG@5 dips slightly with coarse_to_fine** (−0.018) — the section boost can
   pull a same-section-but-lower-relevance leaf above the primary. Tune the cf
   weight (0.3) or apply it only at recall@10 stage in R4.
4. **Math glyph-soup** (§9) still caps lexical on symbol-heavy queries — unchanged.

## RECOMMENDATION (for the go/no-go)
**GO on structure-aware hybrid retrieval for Tu.** It is feasible, fast (~70 ms
warm hybrid; ~1.8 s with rerank), and cheap (~$0.0015/query), and it **beats the
naive baseline decisively on the dimensions that matter for a tutor** — it returns
the *right typed, labeled, source-traceable unit ranked first* (MRR 0.86–0.91,
exact-label-hit up to 0.50, traceability ≈1.0), where the naive baseline can only
get near the page (MRR 0.54, traceability 0). The smallest trustworthy build for
#50: A's deterministic skeleton → C's lexical+vector+type/label hybrid (the ~70 ms
core) → optional rerank for ranking-sensitive turns → B's edges for structural/
neighborhood answers. Reconciled headline figure agreed with D: **recall@5 ≈ 0.82,
MRR ≈ 0.86 (hybrid); ≈ 0.86 / 0.91 with depth.**

## NEXT (R4 if any)
- From **D:** fix/​document the `load_gold_from_db` page_pdf omission so no track
  silently re-hits the R2 artifact.
- Track C: tune coarse_to_fine weight (the −0.018 nDCG dip); try a structural
  *answer path* (return section+contained leaves as a unit) for the structural
  category rather than ranked leaves; a cheaper cross-encoder reranker to push
  rerank latency under 1 s; §17 per-query failure attribution with D.

---

# ROUND 2 (superseded by R3's reconciled numbers) — provenance
R2 produced the first scored bake-off (hybrid recall@5 0.583, +rerank 0.656) and
the ablation (lexical+vector backbone; type/label boosts +0.057; rerank biggest
lift; graph expansion −0.067). **The 0.583 was depressed by the `page_pdf`
gold-loading bug fixed in R3** (page fallback never fired); on the corrected scorer
+ frozen corpus the figure is 0.816, matching D. R2's qualitative conclusions
(structure returns the right typed unit; lexical essential alongside vector; rerank
the biggest lift; graph expansion needed gating) all held and are quantified above.

# ROUND 1 (substrate stand-up) — provenance
R1 stood up the substrate on a fitz_extract fallback (A empty): 90 structured + 40
baseline chunks, primitives, 5-probe sanity. Swapped to A's canonical a_nodes in R2.

## Files (track-c/)
- `extract_slice.py` — R1 fallback extractor (fitz, §8 regexes).
- `baseline.py` — naive fixed-window chunker.
- `embed.py` — OpenAI text-embedding-3-small (1536-d).
- `labels.py` — A↔D gold-label seam (subsection/proof minting).
- `build_index.py` — writes c_chunks + c_baseline_chunks (source a_nodes→seed→fitz; §12 section summaries).
- `retrieve_r2.py` — R3 retriever: resilient shared conn + embed cache, hybrid, INTENT-GATED graph expansion, COARSE-TO-FINE, rerank, ablation knobs.
- `rerank.py` — Claude (claude-haiku-4-5) reranker, latency-tuned (pool 12 / 180-char / max_tokens 128).
- `run_eval.py` — R3 RECONCILED bake-off: C vs D-reference on the identical scorer + frozen corpus + depth variants; persists d_results/d_speed_cost (match_mode=auto; file-gold for page_pdf).
- `score_baseline_pages.py` — R1 page-aware (±1) baseline scorer (kept).
- `bakeoff.py` — R1 5-probe sanity bake-off.
- `GOLD_CONTRACT.md` — R1 gold-format coordination (page-range ask, honored).
- `_vendor_{harness,metrics,ref_retriever}.py`, `_vendor_{queries,gold}.json` — D's harness/metrics/reference-retriever/gold consumed read-only (origin/spike/eval-efficiency) for reproducibility.

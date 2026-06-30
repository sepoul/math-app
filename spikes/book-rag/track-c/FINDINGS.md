# Track C — Indexing & hybrid-retrieval bake-off — FINDINGS

Scope/contract: issue **#57** (Track C). Leads on **the headline result**.
Tables: `c_chunks`, `c_baseline_chunks`. Consumes `a_*`/`b_*` and Track D's
`d_queries`/`d_gold`. Bucket: `track-c/`.

**Question (the headline):** does coarse-to-fine, structure-aware hybrid
retrieval (lexical FTS + pgvector + metadata/type boosts + rerank) **beat a
naive fixed-window chunk-embedding baseline** on Tu's queries — and which
signals carry the weight?

---

# ROUND 2 — THE HEADLINE (scored bake-off + ablation + rerank). VERDICT: structured-hybrid wins decisively.

R2 unblocked on all deps: A's canonical `a_nodes` (143), D's gold (`d_queries` 26
+ `d_gold` 66 graded, 65/66 carrying a real `a_nodes` node_id + a pdf page), and
B's edges (`b_node_edges` 150: contains/parent_of/next/previous/proven_by; B's
`references` edges not yet present — graph expansion walks the live edges).

## The two systems (rebuilt from A)
- **Structured index** `c_chunks`: **141 units** (28 section/subsection + 113
  leaf) sourced from **`a_nodes`** (`--source a_nodes`), adopting A's node_ids
  (`book.sub7.5.theorem117`) and heading_path (§7 is under **Chapter 2** — R1's
  "Chapter 1" was wrong; corrected). §12 contextualized `embed_input`; section
  nodes embed a deterministic **summary** (heading path + contained labels) —
  fixes R1's 8192-token cap with no LLM call. `text-embedding-3-small` (1536-d).
- **Naive baseline** `c_baseline_chunks`: 40 fixed ~450-word windows, no
  structure, embedded identically.
- All 37 distinct gold node_ids are matched by a `c_chunks` node_id (built from
  the same A skeleton), so structured runs score on the strongest key (node_id).

## HEAD-TO-HEAD (D's harness, label/node_id match, k=10, macro over 26 queries)

| run_label | recall@5 | MRR | nDCG@5 | exact-label-hit | source-trace | warm p50 |
|---|---|---|---|---|---|---|
| naive_baseline (vec) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | — |
| naive_lexical | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | — |
| lexical_only | 0.263 | 0.288 | 0.251 | 0.192 | 1.000 | 34 ms |
| vector_only | 0.474 | 0.523 | 0.406 | 0.269 | 1.000 | 37 ms |
| lex+vec | 0.526 | 0.578 | 0.471 | 0.308 | 1.000 | 73 ms |
| +type_boost | 0.554 | 0.597 | 0.506 | 0.385 | 1.000 | 72 ms |
| **hybrid_full** | **0.583** | **0.663** | **0.534** | **0.423** | **1.000** | 73 ms |
| +graph_expansion | 0.517 | 0.645 | 0.489 | 0.423 | 1.000 | 143 ms |
| **+rerank** | **0.656** | **0.738** | **0.639** | **0.577** | **1.000** | 3855 ms |

The naive baseline scores **0.000 on every metric** because D's harness matches on
`node_id`/`label` and a fixed window has **neither** — it literally cannot name
the unit it retrieved. That is itself the headline finding: structure-aware
retrieval can *identify and return the formal object* (Theorem 7.7, its proof);
the naive baseline returns an unlabeled text window that the eval (and a downstream
agent) cannot ground. **Every structured result is source-traceable (1.000)**;
the baseline is 0.000 (no heading_path/page-as-hierarchy).

## Is the baseline really useless? No — page-aware scoring (the honest gap)

To not overclaim, we scored both systems on a **page-proximity** match (a result
"hits" if its pdf page is within ±1 of a gold item's page) — D shipped a pdf page
on every gold row exactly for this (the R1 GOLD_CONTRACT ask). This reuses D's
recall/MRR/nDCG *definitions*, only swapping the match predicate; applied to both
systems for a like-for-like read (`track-c/score_baseline_pages.py`):

| system | recall@5 (page±1) | MRR (page±1) |
|---|---|---|
| naive_baseline (vec) | **0.892** | 0.728 |
| structured hybrid_full | 0.867 | **0.891** |
| structured +rerank | **0.927** | **0.923** |

**What this shows:** on *coarse page location*, the naive baseline is genuinely
competitive on recall (0.892) — the slice is small and term-dense, so a vector
window often lands on the right page. **Where structure wins is RANKING QUALITY
and UNIT IDENTITY**: MRR 0.891/0.923 (structured) vs 0.728 (naive) — structured
puts the *right typed unit first*; and only structured can answer "which theorem
/ which definition / return the proof", which the label/node_id table (0.000 for
naive) captures. So the verdict is nuanced and honest: *naive gets you near the
page; structure gets you the right object, ranked first, with a traceable path.*
(per spec §17: for math books, segmentation/structure matters more than the
embedder — borne out here.)

## ABLATION — which signal carries the weight (Δ vs hybrid_full)

| signal removed / added | Δrecall@5 | ΔMRR | ΔnDCG@5 |
|---|---|---|---|
| lexical_only (drop vector) | −0.321 | −0.375 | −0.283 |
| vector_only (drop lexical) | −0.109 | −0.140 | −0.127 |
| lex+vec (drop type+label boosts) | −0.058 | −0.085 | −0.062 |
| +type_boost (drop label boost) | −0.029 | −0.067 | −0.028 |
| +graph_expansion | −0.067 | −0.019 | −0.044 |
| **+rerank** | **+0.073** | **+0.075** | **+0.106** |

Read-out:
1. **Lexical + vector are the backbone.** Removing vector (lexical_only) costs the
   most (−0.321 recall) — vector carries conceptual queries; but lexical is
   essential too (vector_only loses −0.109), confirming §13 "embeddings are not
   the whole system." Their *fusion* (lex+vec) beats either alone.
2. **Type + label boosts add real, cheap lift** (+0.057 recall over lex+vec,
   +0.115 exact-label-hit: 0.308 → 0.423). The structure-aware metadata signal
   the spec predicts carries weight for math — confirmed.
3. **LLM rerank is the single biggest lift** (+0.073 recall, +0.106 nDCG@5,
   +0.154 exact-label-hit → 0.577) — and the biggest latency cost.
4. **Graph expansion (as built) slightly HURT** recall (−0.067): injecting one-hop
   neighbors of the top-5 seeds displaced relevant direct hits within k. It helped
   `graph_expansion`-category MRR (0.79) but globally it over-fires. Fix: gate
   expansion to graph_expansion-intent queries only, or rank neighbors strictly
   below their seed. A real finding, not noise.

## BY CATEGORY (recall@5 | MRR): naive vs hybrid_full vs +rerank
| category | naive | hybrid_full | +rerank |
|---|---|---|---|
| direct | 0.00 / 0.00 | **0.88 / 0.84** | 0.88 / 0.94 |
| conceptual | 0.00 / 0.00 | 0.57 / 0.67 | **0.71 / 0.71** |
| structural | 0.00 / 0.00 | 0.31 / 0.34 | 0.37 / 0.42 |
| graph_expansion | 0.00 / 0.00 | 0.44 / 0.79 | **0.55 / 0.88** |

- **direct** (label lookups, "Theorem 7.7") is the strongest — exactly where
  structure+label-boost should win, and it does (0.88).
- **structural** ("which defs are in §7.5", "what comes after Theorem 7.7") is the
  weakest (0.31–0.37): these need graph/sibling traversal, not ranked retrieval.
  This is where C should lean on B's `next`/`contains` edges as a *first-class
  answer path* (R3), not just an expansion nudge.

## SPEED / COST (warm, single reused connection)
- **Warm per-query latency** (the R1 plumbing fix landed — one autocommit
  connection + 15s statement_timeout + reconnect-retry): lexical/vector **~34–37
  ms**, hybrid **~73 ms**, +graph **~143 ms**. The query embedding API call is
  **~360 ms** (cached per query text). Rerank adds **~3.7 s/query** (the Haiku call).
- **Index build** (`build_index.py --source a_nodes`): ~14 s end-to-end; embedding
  181 units (141 struct + 40 base) ≈ 60k tokens, ~$0.0015.
- **Rerank cost** (`claude-haiku-4-5`, one call ranks the top-20/query): 26 queries
  = 54,414 in + 7,412 out tokens, **~$0.092 total (~$0.0035/query)**. Cheap enough
  to run inside a daily synthesis pass; the latency (not the $) is the constraint.
- **Caveat (latency artifact):** the shared Supabase pooler was intermittently slow
  during one run (`naive_baseline` p50 spiked to 335 ms; an earlier full run hung on
  a stalled connection — fixed by the statement_timeout + reconnect). Warm SQL cost
  is tens of ms; the seconds are the embedding round-trip + (optionally) rerank.

## BLOCKERS / RISKS
1. **Graph expansion needs redesign** (own finding) — globally additive injection
   hurt recall. R3: make it intent-gated + a dedicated structural-answer path over
   B's edges, scored below seeds.
2. **Baseline is unscoreable on label/node_id gold by construction** — we scored it
   honestly via page-proximity (above). The two views (label/node_id vs page) tell
   the real story together; reporting only one would mislead.
3. **B's `references` edges not yet live** — graph_expansion walks
   contains/next/previous/proven_by only. "Which proofs reference this lemma" (§14)
   waits on B's resolved references.
4. **nDCG under page-scoring can exceed 1** (a quirk of the page-match `gain` vs a
   single-page IDCG when several windows hit one high-relevance page) — treat the
   page-nDCG column as directional, not absolute; the label/node_id nDCG@5 column
   is the rigorous one.
5. **Math glyph-soup** (§9) still caps lexical on symbol-heavy queries — unchanged.

## NEXT (R3 — what Track C needs / will do)
- **From B:** `references`/`referenced_by` edges to make structural + graph_expansion
  categories first-class (they are C's weakest at 0.31–0.55).
- **From A:** confirm the bold-inline `definition` nodes (A added 5; "what is X"
  direct queries lean on them) and any §7 inline `Exercise 7.11` A didn't capture.
- **From D:** if useful, add `gold_pdf_start/end` as table columns (currently only
  in the file-mirror) so page-scoring reads the table, not the JSON.
- **Track C R3 plan:** (1) redesign graph expansion as an intent-gated structural
  path over B's edges (target the weak structural category); (2) tune the rerank
  pool/weights and try a cheaper cross-feature reranker to cut the 3.7 s/query;
  (3) coarse-to-fine: retrieve sections first, then leaves within them (§12) — not
  yet exploited; (4) ship the §17 failure-attribution per missed query with D.

---

# ROUND 1 (substrate stand-up) — kept for provenance
R1 stood up the retrieval substrate on a **fitz_extract fallback** (A's `a_nodes`
was empty at R1): 90 structured chunks (4 section + 86 leaf) + 40 baseline,
embedded 1536-d, with lexical/vector/first-hybrid primitives and a 5-probe sanity
bake-off. R1 found type/label boosts demonstrably re-rank the right unit and
lexical is essential alongside vectors — both confirmed quantitatively in R2. R1's
source was swapped for A's canonical `a_nodes` in R2 behind the same code
(`build_index.py` source preference a_nodes→seed→fitz).

## Files (track-c/)
- `extract_slice.py` — R1 fallback structured extractor (fitz, §8 regexes).
- `baseline.py` — naive fixed-window chunker.
- `embed.py` — OpenAI `text-embedding-3-small` (1536-d) helper.
- `labels.py` — A↔D label seam (subsection/proof gold-label minting).
- `build_index.py` — writes c_chunks + c_baseline_chunks (source a_nodes→seed→fitz; §12 summaries).
- `retrieve.py` — R1 primitives (per-call connection).
- `retrieve_r2.py` — R2 retriever: shared+resilient connection, embed cache, hybrid, graph expansion, rerank, ablation knobs.
- `rerank.py` — Claude (`claude-haiku-4-5`) reranker over top-20 (ranks only, never invents).
- `run_eval.py` — R2 scored bake-off + ablation + rerank via D's harness; persists d_results/d_speed_cost.
- `score_baseline_pages.py` — page-aware (±1 pdf page) scoring so the label-less baseline is comparable.
- `bakeoff.py` — R1 5-probe sanity bake-off.
- `GOLD_CONTRACT.md` — R1 gold-format coordination for Track D (page-range ask honored).
- `_vendor_{harness,metrics}.py`, `_vendor_{queries,gold}.json` — D's harness/metrics/gold consumed read-only (from origin/spike/eval-efficiency).

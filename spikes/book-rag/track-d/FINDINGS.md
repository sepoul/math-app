# Track D — Eval harness, "is it efficient?", speed & cost — FINDINGS

Scope/contract: issue **#57** (Track D). Leads on **speed/cost + the verdict**.
Owns the **measuring stick**, not a retriever. Tables: `d_*`. Bucket: `track-d/`.
Branch: `spike/eval-efficiency`.

**Question:** what does "efficient on my book" mean, measurably — and what's
the go/no-go?

> R1 priority was to **unblock Track C**. Done — 26 queries + 66 graded gold rows
> published to `d_queries`/`d_gold` and mirrored to `../queries/{queries,gold}.json`.
> C scores against them via `track-d/harness.py::evaluate(retrieve_fn, run_label)`.

---

# R3 — reconciled to ONE agreed number + final efficiency picture

**The reconcile is resolved, the bake-off has one agreed table, the §17
miss-collapse is quantified, and the speed/cost ledger has a full-book
projection. Standing read: GO.** All scored through one harness
(`track-d/bakeoff.py`) under one explicit rule.

## R3.0 — RECONCILE: the 0.816 vs 0.583 gap was matching strictness, not quality

R2 cited refD recall@5 **0.816**; C cited its hybrid **0.583**. Scoring BOTH
through Track D's harness pinned the cause exactly:
- **0.816** = the page-overlap *fallback* applied to a structured retriever — too
  generous (credits any chunk on the gold's page, not the right unit).
- **0.583** = strict node_id/label match (the right *unit*) — what a structured-RAG
  verdict should measure. Reproduced C's 0.583 to the digit (`hybrid_full` strict)
  and its 0.656 (`+rerank` strict).

**AGREED RULE (now applied identically to all runs):**
- label-bearing retrievers (all structured + ablations) → **strict** (exact
  `a_nodes` node_id OR exact label);
- the label-less **naive baseline** → **page-overlap** (its only fair rule);
- gold = all relevance ≥ 1 (graded); nDCG uses the grades.
- **Label is the freeze-stable join key.** A's R3 freeze renumbered node_id
  suffixes (`theorem117`→`theorem123`) while C's `d_results` kept the pre-freeze
  ids; the matcher joins on label, so the score is invariant to the renumber
  (verified: strict scores identical before/after the gold remap). Gold is
  re-mapped to the frozen 159-node corpus (`map_gold.py`, now **66/66** — A added
  the `Exercise 7.11` node, closing the R2 coverage gap).

This is not "simplicity wins": under the one rule, **C's elaborate hybrid + rerank
is the best config and beats the reference yardstick** (refD 0.554 strict). The
rerank earns its keep.

## R3.1 — THE ONE AGREED BAKE-OFF (cite the `+rerank` row)

Structured = strict (node/label); baseline = page-overlap. Macro over 26 queries.

| run_label | mode | recall@1 | recall@5 | recall@10 | MRR | nDCG@5 | exact-label | trace |
|---|---|---|---|---|---|---|---|---|
| **`+rerank`** ← **CITE** | strict | 0.346 | **0.656** | 0.742 | **0.738** | **0.639** | **0.577** | 1.000 |
| `hybrid_full` | strict | 0.330 | 0.583 | 0.742 | 0.663 | 0.534 | 0.423 | 1.000 |
| `+type_boost` | strict | 0.301 | 0.554 | 0.742 | 0.597 | 0.506 | 0.385 | 1.000 |
| `refD_structured_hybrid` (yardstick) | strict | 0.340 | 0.554 | 0.726 | 0.637 | 0.539 | 0.462 | 1.000 |
| `+graph_expansion` | strict | 0.330 | 0.517 | 0.650 | 0.645 | 0.489 | 0.423 | 1.000 |
| `lex_vec` | strict | 0.263 | 0.526 | 0.716 | 0.578 | 0.471 | 0.308 | 1.000 |
| `vector_only` | strict | 0.170 | 0.474 | 0.690 | 0.523 | 0.406 | 0.269 | 1.000 |
| `naive_baseline` | page | 0.187 | 0.718 | 0.822 | 0.540 | 0.482 | 0.000 | 0.000 |

**The verdict figure: C's `+rerank`, strict — recall@5 0.656, MRR 0.738, nDCG@5
0.639, exact-label-hit 0.577, traceability 1.000.**

**Structure vs naive, apples-to-apples (both page-overlap — the only rule the
label-less baseline can be scored under):**

| run | recall@5 | MRR | nDCG@5 | exact-label | trace |
|---|---|---|---|---|---|
| `+rerank` (page) | **0.869** | **0.897** | **0.784** | **0.577** | **1.000** |
| `naive_baseline` (page) | 0.718 | 0.540 | 0.482 | 0.000 | 0.000 |

Structure wins decisively even when the baseline gets the generous rule:
**MRR +0.357, exact-label +0.577, traceability +1.000.** The naive baseline gets
*near* the answer by page (recall@5 0.718) but cannot rank it, name it, or trace
it — the §17 capabilities are 0.

> Note: `naive_baseline` strict-row recall@5 (0.718, page) vs structured strict
> (0.656) is NOT comparable — page-overlap is a looser match than exact
> node/label. The honest comparison is the apples-to-apples page row above.

## R3.2 — §17 MISS-COLLAPSE (the core go/no-go evidence)

Reference (no rerank, no graph) → C's `+rerank`, on A's frozen corpus, agreed rule:

| | misses | hits top-3 | breakdown |
|---|---|---|---|
| `refD_structured_hybrid` | 10 | 16 | weak_vector 4 · metadata_rerank 4 · proof_boundary 1 · graph_expansion 1 |
| **`+rerank`** | **6** | **20** | weak_vector 5 · graph_expansion 1 |

**Net −4 misses, 0 newly broken.** Fixed by rerank: **D-012** (conceptual),
**D-019** (the proof-attachment query — proof_boundary→ok), **D-022 & D-026**
(structural, metadata_rerank→ok). **The entire `metadata_rerank` bucket (4)
collapsed** — reranking did exactly its job; UPSTREAM(A/B) failures dropped 2→1.
Same −4 / 0-regression result measured vs C's own pre-rerank `hybrid_full`.

Residual 6 misses: 5 `weak_vector` (the right unit not even in the candidate pool
for some neighbor/conceptual queries — wants candidate-set widening or better
embed-input context) + **D-023** `graph_expansion` (the hardest multi-hop
dependency walk — needs deeper bounded expansion on B's edges). These are the
named next levers, not blockers.

## R3.3 — FINALIZED speed/cost ledger (real numbers in `d_speed_cost`)

| stage | metric | slice value | source |
|---|---|---|---|
| extraction | wall seconds | **0.68 s** (slice) | A (`track-a-extraction`) |
| index build | structured chunks | 141 | C / D |
| index build | embed tokens / USD (one-time) | ~43,000 / **~$0.0009** | D-derived |
| query | latency p50 — hybrid (no rerank) | **73 ms** | C (`hybrid_full`) |
| query | latency p50 / p95 — **+rerank** | **3,855 ms / 5,682 ms** | C (`+rerank`) |
| query | raw FTS+pgvector p50 (no embed) | 87 ms | D |
| query | embed $ / query | **~$2e-7** | D |
| query | rerank tokens / $ per query (est) | ~7,600 / **~$0.023** | D estimate (C didn't log actuals) |

**Full-book (430 pp) projection** (`run_label='fullbook_projection'`, ~13.9× page
scale; per-query cost is index-size-insensitive so it does NOT scale):

| metric | value |
|---|---|
| extraction | **~6.5 s** (A's own projection) |
| index build | ~1,955 chunks, ~600K embed tok, **~$0.012 one-time** |
| per-query latency | hybrid ~73 ms · **+rerank ~3.9 s** |
| per-query $ | embed ~$2e-7 · **rerank est ~$0.023** |

**"Fits in a daily synthesis pass?" — YES, with one lever to watch.**
- One-time index of the whole book: **~$0.012 and a few seconds.** Negligible.
- A no-rerank hybrid query is **~73 ms and ~$2e-7** — run thousands per synthesis,
  effectively free.
- The **`+rerank` query is ~3.9 s and ~$0.023** — the LLM rerank call is the only
  real cost line. For a *daily* pass issuing a handful of book lookups, ~$0.02–0.10
  and a few seconds total is comfortably within budget. If a synthesis ever needs
  hundreds of reranked lookups, gate rerank to the top-N ambiguous queries (rerank
  buys +0.073 recall@5 / −4 misses; spend it where ordering is contested).

## R3.4 — `page_pdf` promoted to a real `d_gold` column (C asked)

`d_gold` now has real `page_pdf` + `page_printed` columns (additive
`ADD COLUMN IF NOT EXISTS`), backfilled on all 66 rows; `load_db.py` writes them
and `harness.load_gold_from_db()` reads them. Page-aware scoring is now clean off
the table (no JSON side-channel).

## R3.5 — STANDING GO / NO-GO read (control plane finalizes in SYNTHESIS.md)

**GO.** On Tu's hard slice, with A's frozen extraction + C's `+rerank` hybrid:
- **Feasibility (A):** ✓ 159 typed nodes; all 37 gold nodes located, indexed,
  page-mapped; the one R2 extraction gap (`Exercise 7.11`) closed.
- **Quality:** ✓ `+rerank` strict recall@5 0.656 / MRR 0.738 / exact-label 0.577 /
  traceability 1.000; beats naive decisively on every ranking + §17 axis; rerank
  collapses 4 of 10 misses with 0 regressions.
- **Speed/cost:** ✓ ~$0.012 one-time full-book index; hybrid query free; rerank
  ~$0.023/query — fits a daily pass; gate rerank if volume grows.
- **Caveats / risk register for #50:** (1) **recall ceiling** — strict recall@5
  is 0.66, not 0.9; 5 residual `weak_vector` misses want a wider candidate pool /
  better contextual embed-input; (2) **multi-hop graph expansion** (D-023) is the
  weakest capability — needs deeper bounded walks on B's edges; (3) **rerank
  latency** (~3.9 s) is the one cost lever — keep it gated. None are blockers; all
  are known, named, and measured.

---

# R2 — the stick turned into numbers (spec §16–§17)

**Headline: structure-aware hybrid beats the naive baseline on every quality
axis, and with A's extraction + C's indexing now complete, the residual failures
are RANKING problems, not missing-content problems.** Detail below.

## R2.1 — gold mapped to A's real node_ids

A's canonical nodes are live (run `track-a-r1`, 143 nodes, `book.sec*/sub*.*`
ids). `track-d/map_gold.py` resolved **65 / 66 gold labels → real `a_nodes.node_id`**
(re-loaded into `d_gold`; 0 dangling refs). Resolution rules built from A's actual
scheme: formal-env labels match verbatim; `subsection N.M …`→`book.subN.M`; proofs
(A labels every proof `'Proof'`) resolve via the `proves` field — e.g.
`"Proof of Theorem 7.7"`→`book.sub7.5.proof118`. **Page anchors + labels kept**, so
C's label-less naive baseline still scores (page-overlap mode).

- **The one unresolved gold (D-007 secondary, `Exercise 7.11`, rel=1):** Tu prints
  this as an *inline starred exercise mid-§7.6*, and A merged it into surrounding
  prose rather than minting a node — a real extraction gap, kept as page-anchored
  gold so it still penalizes a miss. Flagged to A.
- **Seam note (resolved during R2):** C re-indexed mid-round onto A's `book.*`
  node_id namespace (was a private `c.tu.*` namespace earlier) and now indexes
  subsections + definitions + proofs. **All 37 distinct gold node_ids are present
  in C's `c_chunks`, all embedded** — so scoring now matches on EXACT node_id, not
  just label.

## R2.2 — head-to-head + ablation (refD reference retriever on the live corpus)

> Track C had not written `d_results` when R2 ran, so to produce verdict numbers
> NOW I built a **reference retriever** (`track-d/ref_retriever.py`) over C's live
> `c_chunks`/`c_baseline_chunks` — lexical FTS + pgvector + type-boost fusion, and
> a naive fixed-window-vector baseline. **This is a measurement instrument, not
> C's deliverable**; when C's runs land, `score_runs.py --score-existing <label>`
> scores them off `d_results` with the same metrics. All runs persisted to
> `d_results` (+ `d_speed_cost`). Macro over 26 queries:

| run_label | recall@1 | recall@5 | recall@10 | MRR | nDCG@5 | exact-label-hit | traceability |
|---|---|---|---|---|---|---|---|
| **refD_structured_hybrid** | 0.444 | **0.816** | 0.904 | **0.758** | **0.682** | **0.462** | **1.000** |
| refD_naive_baseline | 0.187 | 0.718 | 0.822 | 0.540 | 0.482 | 0.000 | 0.000 |
| refD_no_vector (lex+boost) | 0.244 | 0.295 | 0.333 | 0.314 | 0.281 | 0.231 | 1.000 |
| refD_no_lexical (vec+boost) | 0.347 | 0.816 | 0.904 | 0.689 | 0.634 | 0.346 | 1.000 |
| refD_no_type_boost (lex+vec) | 0.367 | 0.729 | 0.924 | 0.707 | 0.587 | 0.346 | 1.000 |

**Structured-hybrid vs naive — the gap (where structure earns its keep):**
- **MRR +0.218, nDCG@5 +0.200** — structure ranks the *right unit* higher, not
  just "a chunk on the right page". recall@5 gap is smaller (+0.098) because the
  naive baseline does get *near* the answer by page; it just can't rank or name it.
- **exact-label-hit +0.462, traceability +1.000** — the decisive §17 capabilities.
  The naive baseline scores **0.000** on both: its fixed-window chunks carry no
  label and no `heading_path`, so it can neither answer "Theorem 7.7" by label nor
  return a traceable path back to the source unit. Structure gives both for free.

**Ablation — which signal carries the weight (Δ vs full hybrid):**
- **vector dominates: −0.521 recall@5 / −0.401 nDCG@5 when removed.** On this slice
  (single book, paraphrase-heavy conceptual queries), dense retrieval is the
  workhorse for recall.
- **lexical: ~0 recall@5 but it carries label/exact matching** — exact-label-hit
  drops 0.462→0.346 and MRR 0.758→0.689 without it (it ranks the exactly-named
  unit first). It's an ordering/precision signal here, not a recall signal.
- **type-boost: −0.087 recall@5 / −0.095 nDCG@5** — a modest, real lift.

> Caveat on the magnitude: the refD retriever uses a flat 0.5·vec+0.5·lex+boost
> fusion with **no reranker and no graph-edge expansion**. C's `+rerank` and B's
> edges should lift the ranking-bound failures below (and they're the next runs to
> score). These numbers are a *floor* for structured-hybrid, and the structure-vs-
> naive direction is already unambiguous.

## R2.3 — §17 failure attribution (refD_structured_hybrid; primary gold not in top-3)

**16 / 26 queries hit primary gold in top-3.** The 10 residual failures:

| bucket | n | side | example |
|---|---|---|---|
| weak_vector | 4 | RETRIEVAL (C) | "tangent vectors as derivations", "gluing a square to a torus" |
| metadata_rerank | 4 | RETRIEVAL (C) | "what comes after Theorem 7.7", "list subsections of §3" |
| theorem_proof_boundary | 1 | UPSTREAM (A/B) | "proof attached to Proposition 7.3" |
| graph_expansion | 1 | UPSTREAM (A/B) | "results that depend on the quotient construction" |

**UPSTREAM (A/B structure/extraction/graph): 2 · RETRIEVAL (C ranking): 8.**

Interpretation — and this is the load-bearing R2 finding: now that A's extraction
and C's coverage are **complete** (all 37 gold nodes indexed), failures have moved
OFF "the node is missing" and ONTO **ranking**:
- The 4 `metadata_rerank` cases are *structural* queries where the right unit IS in
  the top-10 but below rank 3 → exactly what a **reranker (C's `+rerank`) and
  graph-edge boosts (B's `next`/`contains`/`proven_by`)** are for. The refD
  retriever has neither, so this bucket should shrink when C/B's signals are scored.
- The 4 `weak_vector` cases are conceptual/neighbor queries where flat embedding
  similarity over-weighted the wrong section — a fusion-weight / rerank issue.
- Only 2 are genuinely upstream: one proof-unit not surfaced, one graph-walk the
  flat retriever can't do (needs B's edges).

This **confirms the spec §17 thesis on Tu**: once segmentation/structure is right
(it is — A nailed it), the remaining wins come from **ranking/fusion/graph**, not
from swapping the embedding model. Re-run after C's `+rerank`/B-edges land to watch
the 8 retrieval-side failures collapse.

## R2.4 — speed / cost ledger (real numbers, in `d_speed_cost`)

| stage | metric | value | note |
|---|---|---|---|
| query | latency p50 / p95 | **1.10 s / 1.17 s** | end-to-end per query (structured_hybrid) |
| query | raw retrieval p50 / p95 (no embed API) | **87 ms / 184 ms** | FTS+pgvector only; remote Supabase RTT |
| query | embed tokens / query | ~11 | the query string |
| query | embed $ / query | **~$2e-7** | text-embedding-3-small @ $0.02/Mtok |
| index | structured + baseline chunks | 141 + 40 | C's slice corpus |
| index | embed tokens (one-time) | ~43,000 | whole-slice corpus |
| index | embed $ (one-time) | **~$0.0009** | trivial |

**The ~1 s/query latency is almost entirely the OpenAI embedding network round-trip**
(raw DB retrieval is <0.2 s, and that's remote-Supabase RTT — a co-located DB is
single-digit ms). Query-embedding is cacheable/batchable. **Verdict on efficiency:
comfortably inside a daily-synthesis budget** — index build is a fraction of a cent,
per-query cost is negligible, and the only latency lever is the embed call.
*(A's extraction time + C's rerank token/$ are theirs to write into `d_speed_cost`
under `extraction`/`query` stages; not yet present.)*

## R2.5 — go / no-go signal (control plane finalizes in SYNTHESIS.md)

On the evidence so far: **GO**, with the caveat that the win is in *structure +
ranking*, not embeddings.
- **Feasibility (A):** ✓ slice extracted to 143 typed nodes; all 37 gold nodes
  located & indexed; printed-page mapping correct.
- **Quality:** ✓ structured-hybrid beats naive on every axis; the two §17
  signature capabilities (exact-label-hit, source-traceability) are **0 → strong**
  purely from structure.
- **Speed/cost:** ✓ ~$0.0009 one-time index, ~$2e-7/query, sub-200 ms DB retrieval.
- **Where it breaks (risk register for #50):** (1) inline/un-numbered items A
  merges into prose (the `Exercise 7.11` gap) — a coverage risk for "find this
  specific item"; (2) structural/graph queries need a reranker + the real graph
  edges to rank right (8 of 10 residual misses) — so **B's edges and a reranker are
  load-bearing, not optional**; (3) proof-unit surfacing.

---

## R1 deliverables (the stick is live)

| deliverable | where | state |
|---|---|---|
| 26 grounded queries (4 categories) | `d_queries` + `queries/queries.json` | shipped |
| 66 graded gold labels | `d_gold` + `queries/gold.json` | shipped |
| metrics (recall@k, MRR, nDCG@k, exact-label-hit, source-traceability) | `track-d/metrics.py` | importable |
| scoring harness + `d_results`/`d_speed_cost` writer | `track-d/harness.py` | shipped |
| file-mirror → DB loader | `track-d/load_db.py` | ran clean |
| self-test (oracle vs degraded mock) | `track-d/selftest.py` | passes |

## Query suite (grounded in Tu) — `d_queries`

| category | n | probes (spec §14) |
|---|---|---|
| `direct` | 8 | exact label / definition ("Theorem 7.7", "definition of the quotient topology") |
| `conceptual` | 8 | paraphrase / topic ("what makes a map a quotient map", "C∞ vs analytic") |
| `structural` | 6 | neighbors & contents ("what comes after Theorem 7.7", "results in §7.5") |
| `graph_expansion` | 4 | bounded dependency walks ("everything needed to prove RP^n is Hausdorff") |
| **total** | **26** | |

## Metrics + gold — `d_gold` (66 rows: rel=2 ×44, rel=1 ×22)

Gold rows per query category: direct 11 · conceptual 23 · structural 17 ·
graph_expansion 15. Graded relevance: **2 = primary/exact answer**,
**1 = relevant/supporting** (nDCG rewards ranking primary above supporting).

- **metrics** (`metrics.py`, pure-python, no DB dep): `recall@k`, `MRR`,
  `nDCG@k` (graded), `exact_label_hit` (rank-1 carries the primary label —
  the "find Theorem 7.7" capability), `source_traceability` (result carries
  `page_pdf_start` **and** non-empty `heading_path`, spec §17 "traceable path
  back to source").
- **gold labelling method**: authored by **reading the Tu PDF directly**
  (PyMuPDF), not from memory; every label verified on its page, every page
  anchored. §7 "Quotients" located in **Chapter 2: Manifolds**, pdf p90–101 /
  printed p71–82 (printed offset = 19 here, but NOT global — gold carries both
  `page_pdf` and `page_printed`). Ch1 §1–§3 = pdf p22–52 / printed p3–33.
  Verified §7 inventory: Prop 7.1, Ex 7.2, Prop 7.3 (+proof cites Prop 7.1),
  Prop 7.4, Ex 7.6, **Thm 7.7** (Hausdorff ⇔ closed graph), Cor 7.8, Thm 7.9,
  Cor 7.10, Ex 7.11–7.13, Prop 7.14, Cor 7.15 (proof = "Apply Corollary 7.10"),
  Prop 7.16. Structural/expansion gold read off actual adjacency + proof text.
- **anchored to STABLE LABELS, not node_ids** (`a_nodes` empty this round):
  `gold_node_id` is null, matching keys on `gold_label` (Tu's `Theorem 7.x` /
  `subsection N.M` / `Definition: …`). Matcher normalizes case/space and prefers
  node_id when present → B/C map labels→node_ids in R2 with **zero gold rewrite**.
- **one soft spot**: two derived proof-node labels (`"Proof of Proposition 7.3"`,
  `"Proof of Theorem 7.7"` — D-019/D-026) depend on Track A's proof-node naming
  (Tu prints bare `Proof.`). Flagged to A. Everything else is a label Tu prints.

**Self-test (mock retrievers, proves the stick discriminates):**

| run | recall@5 | MRR | nDCG@5 | traceability | exact_label_hit_rate |
|---|---|---|---|---|---|
| oracle (returns gold, traceable) | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| degraded (½ gold, mis-ordered, ½ untraceable) | 0.585 | 1.000 | 0.492 | 0.885 | 0.385 |

(recall@1≈0.53 for the oracle is correct — most queries have several gold items,
so one rank-1 slot can't recover all; nDCG@1=1.0 confirms rank-1 is a primary.)

## `d_results` / `d_speed_cost` run convention (what C writes in R2)

One `d_results` row per `(run_label, query_id, rank)`: `retrieved_node_id`
(null till A lands) · `retrieved_chunk_id` · `score` · `signals` jsonb (per-signal
contributions for the ablation + `label`/`page_pdf_start`/`heading_path` so a
result stays self-describing and traceability is scorable). C calls
`harness.evaluate(retrieve_fn, run_label, persist=True)` where
`retrieve_fn(query_text, k) -> list[dict]`; the harness times each query, scores
against gold, writes `d_results` + a `d_speed_cost` latency/quality ledger
(idempotent on `run_label`). **C must reuse this, not invent metrics** (the seam
#57 says to police). Ablation = same retriever under multiple labels with
signals toggled: `hybrid_full` / `hybrid_no_rerank` / `hybrid_no_vector` /
`hybrid_no_lexical` / `hybrid_no_type_boost` / `naive_baseline`.

## §17 failure-attribution decision tree

```
A result is wrong / missing for a query. Why?

0. Is the GOLD right?  (D owns) re-read gold.page_pdf. If wrong → fix d_gold.   [D]

1. Is the right NODE even in the corpus?
   └─ no  → UPSTREAM extraction/structure failure:
      a. heading segmentation  — leaf filed under wrong heading_path           [A §5-6]
      b. PDF reading order      — glyph-soup/column split garbled the statement [A §2-3]
      c. theorem/proof boundary — proof merged/split → "Proof of X" missing
                                  (hits D-019/D-026)                           [A §8]
      d. page mapping           — node ok but page_pdf/printed wrong →
                                  traceability fails though it "hit"           [A §4]
   └─ yes → retrieval-side, go to 2.

2. Node exists but ranked too low / out of top-k. Which signal failed?
      e. weak lexical    — exact label/symbol query missed (FTS)               [C §13]
      f. semantic vector — paraphrase missed (embed input lacked hierarchy)    [C §12-13]
      g. metadata/type   — "what is X" didn't prefer definitions, etc.         [C §13]
      h. reranking       — right candidate reranked down
                           (compare hybrid_full vs hybrid_no_rerank)           [C §13]

3. Structural / expansion query specifically:
      i. graph expansion — missing next/previous/proven_by/references edges,
                           or expansion unbounded (returns the whole section)  [B §10-11]

Rule of thumb (spec §17): for a math textbook, 1a–1d + 3i (segmentation +
structure + graph) usually dominate over 2e–2h (which embedding). The ablation
run-labels isolate 2e–2h; gold page anchors + signals.heading_path isolate
1a–1d; the structural/expansion gold isolates 3i.
```

## Speed/cost ledger (end-to-end slice) — TEMPLATE, filled R2+

Auto-written `query`+`quality` rows come from the harness; A/B/C add stage rows.
"Efficient inside daily synthesis" = index build amortized one-time; recurring
cost = per-query latency + $ (watch any model-based reranker's tokens/$/query).

| stage | metric | value | who |
|---|---|---|---|
| extraction | seconds (slice ≈ 31 pp) | _R2: A_ | A |
| index build | seconds + embedding tokens/USD | _R2: C_ | C |
| query | latency_p50_ms / p95_ms | _R2: harness_ | D/C |
| query | tokens / USD per query (rerank LLM) | _R2: C_ | C |

## Go / no-go recommendation (control plane completes in SYNTHESIS.md)

Verdict template — fill from R2 numbers:
- **Feasibility** (A scorecard): % defs/theorems/proofs recovered & located; page mapping correct.
- **Quality** (head-to-head on this gold): structured-hybrid recall@5 / nDCG@5 / exact-label-hit vs naive baseline; which signal carries it (ablation).
- **Speed/cost** (`d_speed_cost`): extraction / index / query-p95 / $-per-query within daily-synthesis budget? y/n.
- **Failure attribution** (§17 tree): dominant branch (expect segmentation/structure for a math book).
- **Verdict**: GO / NO-GO + smallest trustworthy slice for #50 + risks (math regions, reference resolution, concepts→canonical-object).

## NEXT round — needs from A/B/C

- **A**: `a_nodes.node_id`+`label` map for the slice, esp. proof-node naming
  (D-019/D-026); confirm `heading_path` shape (my traceability check matches it).
- **B**: confirm edge types backing structural/expansion gold (`next`/`previous`
  D-017/D-021, `contains` D-018/D-020/D-022, `proven_by` D-019, references/uses
  D-023–D-026) so attribution branch 3i is checkable.
- **C**: **unblocked now** — wire `retrieve_fn` to `harness.evaluate(..., persist=True)`;
  run `hybrid_full` + `naive_baseline` + ablation labels.
- **D (me) R2**: map gold labels→node_ids once A lands (re-run `load_db.py`);
  stand up the end-to-end speed/cost ledger + per-query $/token capture; score
  C's runs; build the §17 attribution histogram driving the go/no-go.

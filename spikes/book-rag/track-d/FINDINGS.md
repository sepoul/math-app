# Track D — Eval harness, "is it efficient?", speed & cost — FINDINGS

Scope/contract: issue **#57** (Track D). Leads on **speed/cost + the verdict**.
Owns the **measuring stick**, not a retriever. Tables: `d_*`. Bucket: `track-d/`.
Branch: `spike/eval-efficiency`.

**Question:** what does "efficient on my book" mean, measurably — and what's
the go/no-go?

> R1 priority was to **unblock Track C**. Done — 26 queries + 66 graded gold rows
> published to `d_queries`/`d_gold` and mirrored to `../queries/{queries,gold}.json`.
> C scores against them via `track-d/harness.py::evaluate(retrieve_fn, run_label)`.

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

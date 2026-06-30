# Book-RAG Spike — Orchestration Report

_Living report. Control plane: this session. Branch: `spike/orchestration-report`.
Base issue: #57. Spec: `book_only_structured_math_retrieval.md`._

## The question

Is **structured RAG retrieval** feasible, high-quality, and fast enough on the
real book — Tu, *An Introduction to Manifolds* (2nd ed., 430pp native PDF) — to
be the foundation the Mentor Loop epic (#50, esp. #55/#53) rests on?

## Method — a 4×4 fleet

Four persistent workers, each owning one slice of the pipeline and an isolated
Supabase zone, re-engaged (context intact) across four rounds of iterative
refinement. Round themes walk the spec while always treating it as one system:

| Round | Theme | Spec |
|---|---|---|
| R1 | Inspect & extract — the substrate | §1–§9 |
| R2 | Graph & grounding — make the structure trustworthy | §10–§11 |
| R3 | Chunking & hybrid-retrieval bake-off (vs naive) | §12–§15 |
| R4 | Eval, efficiency & the go/no-go verdict | §16–§17 |

| Worker | Track | Branch | Zone (tables) |
|---|---|---|---|
| A | extraction & skeleton | `spike/extraction-skeleton` | `a_*` |
| B | graph, refs, validation | `spike/graph-grounding` | `b_*` |
| C | indexing & hybrid retrieval | `spike/hybrid-retrieval` | `c_*` |
| D | eval harness & efficiency | `spike/eval-efficiency` | `d_*` |

Orchestrator zone: `o_*` tables + `orchestrator/` bucket folder. The shared
slice everyone works (so numbers compare): **Tu Ch1 §1–§3 + Ch7 §7 (Quotients)**.

## What the §1 inspection already established

430-pp native PDF, selectable text; 269-entry embedded outline
(Chapter→§Section→Subsection); separable heading typography; math extracts as
glyph-soup (CM/Symbol/xypic, no images); **Tu labels sections `§N` / subsections
`N.M`** (the spec's generic `^(\d+)\.(\d+)` section regex mis-fires); printed
offset ≈21, non-constant.

---

## Round 1 — Inspect & extract (§1–9) — COMPLETE

All four workers reported; branches pushed. The substrate exists and the
feasibility/speed signal is strong; the decisive quality number (structure vs
naive) is deferred to R2 by design.

| Track | Built | Headline numbers | Cost/speed |
|---|---|---|---|
| **A** extraction | 143 typed nodes (2 ch / 4 §sec / 24 subsec / 113 env); 25/25 proofs linked; 44/45 pages mapped (+19 offset); 584 eq-fragments + 27 crops | label recall+precision 100% _(non-independent — see caveat)_ | **0.7 s / $0** for 45 pp → **~7 s projected full book** |
| **B** graph | 150 deterministic edges; Tu-grammar reference resolver; all 7 §10 invariants proven via perturbation harness | refs **36/36 = 100%** in-slice; 0 invariant violations | **~1 s / $0** |
| **C** retrieval | structured index (90: 4 §sec + 86 leaf) vs naive baseline (40 windows), both embedded (text-embedding-3-small 1536d); lexical+vector+hybrid | 2 structure wins on probes; real scored bake-off → R2 | index 8 s; **$0.0015** embed; **39 ms** warm KNN |
| **D** eval | 26 queries + 66 graded gold (grounded on the PDF); `metrics.py` + `harness.evaluate()`; self-test discriminates | oracle 1.0 vs degraded 0.585 → the stick works | pure-python |

**What R1 establishes**

- **Feasibility + speed: strong GO signal.** The whole structured pipeline —
  extract → graph → index → retrieve — is deterministic, ~seconds, and
  effectively free ($0 extraction/graph; $0.0015 embeddings; 39 ms KNN). Fits
  inside the daily synthesis pass with room to spare.
- **The book's structure comes out cleanly** from Tu's 269-entry outline + typed
  environments, with proof→theorem linkage and page mapping, no LLM.
- **Honest caveat:** A's "100%" shares detection logic with its own ground
  truth. **D's independent gold is the real arbiter** — that test is R2.
- **The hard problem is math:** display equations extract as out-of-order
  glyph-soup (584 over-counted fragments); needs 2D bbox-clustering + optional
  vision-LaTeX. Main fidelity risk; symbol queries lean on vector+label for now.

**Tu-specific truths discovered (and reconciled)**

- **§7 "Quotients" is in Chapter 2** (sections numbered continuously book-wide) —
  A + D agree; B/C had assumed Ch1. `a_nodes` is now canonical; all tracks adopt
  A's `book.ch2.s7.*` IDs in R2.
- **Definitions are inline/bold, not numbered environments** (0 `Definition N.M`
  in the slice) → definitional queries must target a section/inline span.
- **"Problem" (listing) vs "Exercise" (body label)** is a real naming split →
  normalized into a label/alias set for refs + gold.
- **Reference accuracy is capped by extraction recall, not the resolver** — now
  A has full recall, R2 should show high resolution on real nodes.

**Decisions carried into R2**

1. `a_nodes` is the canonical corpus: **B** swaps off its hand-seed, **C**
   rebuilds the index `--source a_nodes`, **D** maps gold labels → A's node_ids.
2. **R2 is the decisive round:** C produces the *scored* head-to-head
   (recall@5 / MRR / label-hit / traceability) vs naive, + per-signal ablation +
   an LLM rerank stage + warm-connection latency.
3. Cross-track contracts relayed by the control plane (workers can't message
   each other): C's `GOLD_CONTRACT` → D; D's `harness.evaluate` API → C; A's
   node-ID + proof-node naming → B/D.

## Round 2 — Graph & grounding + the scored bake-off (§10–15) — COMPLETE

The decisive round. Workers re-engaged on their R1 sessions (context intact),
rebuilt on the now-canonical `a_nodes`, and produced the first scored numbers.

**What hardened (substrate):**
- **A:** 584 raw math fragments → **205 true ordered equation regions**;
  vision→LaTeX (`claude-opus-4-8`) ~0.95 confidence; **16 inline definitions**
  recovered (Tu italicizes definienda — no `Definition N.M`); published the
  proof-node scheme + `a_nodes.aliases` (Problem↔Exercise). `a_nodes` → 159.
- **B:** rebuilt on machine nodes — **1,100 edges**, **0 dangling**, **0
  structural invariant violations**; **reference resolution 87/87 = 100%**
  (fixed the Problem↔Exercise alias); published `references` edges + flagged 6
  genuine Track-A recall gaps for §17.

**The bake-off (structured vs naive, D's gold, 26 queries):**

| run | recall@5 | MRR | nDCG@5 | label-hit | trace |
|---|---|---|---|---|---|
| naive_baseline (node_id gold) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| C hybrid_full | 0.583 | 0.663 | 0.534 | 0.423 | 1.000 |
| **C +rerank** | **0.656** | **0.738** | **0.639** | **0.577** | 1.000 |
| D reference retriever (floor) | 0.816 | 0.758 | 0.682 | 0.462 | 1.000 |
| naive, page-aware (±1pp) | 0.892 | 0.728 | — | 0.000 | 0.000 |
| structured +rerank, page-aware | 0.927 | 0.923 | — | 0.577 | 1.000 |

**Reading it honestly:**
- **Structure wins on the capabilities that matter.** Naive scores **0 on
  label-hit and traceability by construction** — a fixed window can't name or
  ground the unit it returns. Page-aware, naive *finds the page* (0.89) but
  structure *returns the right typed unit, ranked first, named, and grounded*
  (trace 1.0). For #55's "redo this exact thing (Hatcher §1.2)" that difference
  is the whole point.
- **LLM rerank is the single biggest ranking lift** (+0.073 recall, +0.106
  nDCG, label-hit 0.423→0.577) at ~$0.0035/query — and D's §17 attribution
  shows **8 of 10 residual misses are ranking-side**, so rerank + B's edges are
  **load-bearing, not optional.**
- **Graph-expansion as built *hurt* (−0.067)** — global neighbor injection
  displaced direct hits → R3 redesigns it as an *intent-gated* path over B's
  edges. Structural-category queries are the weak spot (0.31–0.37).
- **Efficiency is comfortably GO:** warm retrieval 34–143 ms, index $0.0009,
  per-query embed ~$2e-7, rerank ~$0.0035/q; vision→LaTeX run lazily only on
  retrieved regions. **Cost is a non-issue; rerank latency (~3.7 s) is the only
  thing to engineer.**

**The one thing to reconcile (R3 priority):** D's *simple* reference retriever
scored recall@5 **0.816**, but C's *elaborate* hybrid scored **0.583** (+rerank
0.656). Either C's granular indexing + the hurtful graph-expansion costs recall,
or the gold-matching differs. **The verdict must rest on one agreed number** —
C+D reconcile in R3 (node_id-match rigorous, page-match honest secondary).

**Decisions into R3:** (1) C+D converge to the single agreed bake-off figure;
(2) C: intent-gated graph-expansion over B's now-live edges + coarse-to-fine
(§12, unexploited) + tune rerank; (3) B: ship a bounded graph-expansion helper +
close the recall-gap loop with A; (4) A: close the 6 inline `Exercise` recall
gaps + log extraction time; (5) D: re-score C's real runs with aligned matching
+ re-run §17 attribution (watch ranking-side misses collapse).

## Round 3 — Retrieval depth + reconciliation (§12–15) — COMPLETE

- **A** closed all 6 recall gaps (+ found a 7th, `Exercise 3.6 Inversions`) and
  **froze the corpus**: `run_id track-a-r1`, **166 nodes**, fidelity 120/120;
  extraction logged (slice 0.68s, full-book ~6.5s, $0).
- **B** shipped an **intent-gated bounded expansion helper** C imports;
  reference resolution **96/96 = 100%, zero recall gaps**; quantified that
  deterministic edges fully answer *structural* queries (100%) but cap
  *graph-expansion* at 60–75% — the 3 misses are cross-subsection semantic deps
  needing the optional §11 `depends_on` tier.
- **C** deepened retrieval on the frozen corpus: intent-gating **fixed R2's
  −0.067 graph regression** (now neutral, MRR→1.0 on structural/expansion);
  coarse-to-fine +0.030 recall@10; **rerank latency halved** (3855→1789ms) at
  ~$0.0014/q.
- **C + D reconciled the R2 discrepancy** — it was *measurement state, not
  retriever quality*: a gold-loader silently dropped the `page_pdf` column so
  the page-fallback never fired. On one harness, C and D agree to noise.

**The numbers (frozen corpus, 26 queries) — and the honest bracket:**

| run | recall@5 (page-aware) | recall@5 (strict unit) | MRR | label-hit | trace | p50 |
|---|---|---|---|---|---|---|
| naive_baseline | 0.718 | 0.000 | 0.540 | 0.000 | 0.000 | 197ms |
| **C_hybrid** (no LLM) | 0.816 | ~0.58 | 0.862 | 0.423 | 0.981 | **73ms** |
| **C_full** (gated graph + c2f + rerank) | **0.854** | ~0.66 | **0.910** | 0.500 | 0.988 | 1938ms |

> **Read the bracket honestly.** Structure-aware hybrid returns the **right
> place ~0.82–0.86** of the time and the **exact right unit ~0.58–0.66** of the
> time — and *every* result is named + source-traceable (trace ≈ 1.0). The naive
> baseline reaches the right page ~0.72 of the time but **names/grounds/ranks
> nothing** (label-hit 0, trace 0). For #55 ("redo *this* exercise, here") the
> named/traceable unit is the product requirement — the dimension where naive
> scores zero.

**Orchestrator flag (for R4):** C and D both conclude GO but cite different
primary recall (D: strict ≈0.66; C: page-aware ≈0.82–0.86) due to (1) match-mode
choice, (2) a `page_pdf` gold-loader bug, (3) rerank config drift across rounds.
**Not a contradiction — a bracket.** R4 must publish **one canonical table**
(single config, one gold source, both strict + page-aware side by side).

## Round 4 — Eval & verdict _(pending)_

---

## Interim consolidation — after Round 3 (where we stand)

**Verdict trajectory: a confident GO** for structured RAG on Tu, on all three
axes the spike set out to test.

- **Feasibility ✓** — Tu's structure extracts deterministically and completely:
  166 typed nodes, 120/120 environments, proof→theorem links, 100% reference
  resolution, page mapping, 205 equation regions (vision→LaTeX ~0.95). The book's
  formal grammar *is* recoverable into a trustworthy graph, no LLM in the hot path.
- **Quality ✓** — structure-aware hybrid beats a naive fixed-window baseline on
  every axis that matters, decisively on the ones naive *cannot do at all*
  (name the unit, ground to source, rank correctly: naive = 0). Rerank is the
  single biggest ranking lift and **earns its keep** (beats the reference
  yardstick; collapses the entire `metadata_rerank` miss bucket). The §17
  attribution confirms the spec thesis: with extraction solid, **failures live
  in ranking, not segmentation or embedding choice.**
- **Speed/cost ✓** — extraction ~6.5s/full-book/$0; index ~$0.012 one-time;
  hybrid query **73ms** and effectively free; LLM rerank the one cost line
  (~$0.0014–0.023/q, ~1.8s) — gate it to ambiguous queries. **Fits a daily
  synthesis pass with room to spare.**

**What's settled:** the substrate (extraction + graph + grounding), that
structure beats naive, that rerank is load-bearing, that cost is a non-issue,
that it scales to 430pp.

**What R4 closes:** (1) the **one canonical bake-off table** (strict + page-aware
for a single config — resolve the C/D presentation gap); (2) **B's optional
`depends_on` edges** to attack the lone multi-hop miss (D-023) — and a
recommendation on whether semantic edges earn a place in #50; (3) **C widening
the candidate pool / embed-input** for the 5 `weak_vector` misses (the strict-
recall ceiling); (4) the **fix/standardize the `page_pdf` gold loader**; (5) the
final synthesis + risk register for #50/#55/#53.

**What it means for the Mentor Loop (#50):** the foundational dependency this
spike was built to de-risk — *can we ground the loop in structured retrieval
over the book?* — answers **yes**. #55 (book skeleton & grounding) is directly
validated (named, page-traceable units at ~73ms). #53 (bridge canonicalization)
gets a partial answer: structural/reference edges resolve in-track connections
fully, but **cross-subsection conceptual bridges need the semantic-edge tier**
(B's R4 `depends_on` experiment sizes that cost).

## Cross-cutting analysis _(persisted in `o_analysis`; 14 findings across R1–R3)_
## Verdict: GO / NO-GO _(R4 — final)_

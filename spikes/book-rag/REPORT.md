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

## Round 3 — Retrieval depth + reconciliation _(pending)_
## Round 4 — Eval & verdict _(pending)_

---

## Cross-cutting analysis _(accrues each round)_
## Verdict: GO / NO-GO _(R4)_

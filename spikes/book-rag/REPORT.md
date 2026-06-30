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

## Round 2 — Graph & grounding _(pending)_
## Round 3 — Retrieval bake-off _(pending)_
## Round 4 — Eval & verdict _(pending)_

---

## Cross-cutting analysis _(accrues each round)_
## Verdict: GO / NO-GO _(R4)_

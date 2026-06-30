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

## Round 1 — Inspect & extract _(pending)_
## Round 2 — Graph & grounding _(pending)_
## Round 3 — Retrieval bake-off _(pending)_
## Round 4 — Eval & verdict _(pending)_

---

## Cross-cutting analysis _(accrues each round)_
## Verdict: GO / NO-GO _(R4)_

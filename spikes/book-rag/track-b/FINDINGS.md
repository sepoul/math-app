# Track B — Document graph, references & validation — FINDINGS

Scope/contract: issue **#57** (Track B). Leads on **structure quality**.
Tables: `b_*` (consumes `a_*` or the seed fixture). Bucket: `track-b/`.

**Question:** from typed nodes, can we build the graph (`contains`/`parent_of`/
`next`/`previous`/`proven_by`/`has_equation`/`references`), enforce the §10
invariants, and resolve in-text cross-references ("by Theorem 4.7", "Problem
2.16") to node IDs?

Slice: **Tu, Ch1 §1–§3 + Ch7 §7 "Quotients"**. Branch: `spike/graph-grounding`.

**Round-1 answer: YES, and it is cheap and deterministic.** The structural graph
and reference resolution are *not* the risky part of this spike — extraction
completeness (Track A) is. Single hard finding: **reference-resolution accuracy
is capped by extraction recall, not by the resolver.**

## What was built (round 1)
- **Seed fixture** (`seed/seed_s7_quotients.json`, builder `seed/build_seed_s7.py`):
  hand-extracted **44 nodes** of §7 from the PDF (pdf 90–103 / printed 71–84,
  **offset = pdf − 19**), validated against `_shared/schema.py` + 3 equations.
  Built because `a_nodes` was empty at round start. By kind: section 1,
  subsection 7, proposition 5, theorem 2, corollary 3, definition 1, example 5,
  exercise 10 (Problems 7.1–7.9), proof 7, exposition 1, + book/chapter stubs.
- **Graph builder** (`track-b/graph_build.py`): node loader (`a_nodes` first,
  seed fallback) → deterministic edges → reference resolver → §10 invariants →
  writes `b_node_edges` / `b_references` / `b_validation_issues`.
- **Honest ref eval** (`track-b/ref_eval_raw.py`): re-runs the resolver against
  Tu's **genuine §7 prose** (raw PDF text, headers stripped), since seed text is
  partly circular.

## TABLES (row counts)
| table | rows |
|---|---|
| `b_node_edges` | **150** |
| `b_references` | **17** (from seed text; **38** mentions from raw prose) |
| `b_validation_issues` | **0** (clean seed; checks proven live) |

## QUALITY
**Edges by type (150):** contains 43, parent_of 43, next 27, previous 27,
`proven_by` 7 (conf 0.97), `has_equation` 3. All six are **fully deterministic**
from typed nodes — no model.

**Reference resolution on Tu's REAL §7 prose** (Tu grammar: `Kind N.M`; exercises
cited `Problem N.M` but listed bare `N.M`; sections `§N`; chapters `Chapter K`):
- **38 genuine in-text mentions**; **in-slice accuracy 36/36 = 100%**.
- **2 out-of-slice cross-refs correctly DECLINED** (`Corollary A.36`, `Example 5.7`).
- **Headline lesson:** first pass scored 33/37 because **`Corollary 7.8` is cited
  3× in §7 but was missing from the hand-seed** (the resolver was right to not
  resolve it). Adding the node (pdf 94) → 100%. ⇒ **ref accuracy is bounded by
  node completeness, not resolver quality** — Track A's recall drives this.

**Invariant violations (§10): 0 on the clean seed, but all 7 checks are LIVE** —
a perturbation harness breaks each and confirms it fires: `child_before_parent`,
`proof_before_theorem`, `numbering_monotone`, `proof_attachment`,
`printed_page_monotone`, `toc_section_missing_heading`, `header_as_heading`. The
header detector correctly flags "§7 Quotients" repeating across pdf 91–102. The
**real test is Track A's machine-extracted nodes** (boundary/page errors the
clean seed can't have).

## Speed / cost
Full pipeline (load + 150 edges + 38-mention resolve + 7 invariants + PDF header
detect + persist): **~1.0 s** for the slice, **$0 / 0 tokens** — pure
deterministic text processing, comfortably inside a daily synthesis pass.

## Blockers / risks
- **No blocker** — seed fallback kept Track B unblocked (`a_nodes` empty all round).
- **Extraction recall** is the real risk: one dropped node (Cor 7.8) silently
  breaks every reference into it.
- **Tu grammar** (`Problem N.M` vs bare `N.M`; unnumbered bare `Example.` on pdf
  93) is book-specific; encoded here, A must preserve it.
- **Math glyph-soup** pollutes top-margin lines; header detector tolerates it.

## Coordination with A (seam status)
`a_nodes` is **EMPTY** at round-1 end → ran entirely on the seed. Built strictly
against `_shared/schema.py`; live `a_nodes` columns match the `Node` model.
`load_nodes()` reads `a_nodes` first and auto-swaps when populated — **no code
change needed** if A keeps the schema. Node-IDs used: `book.ch1.s7.<env>`
(e.g. `…thm7_7`, `…prf7_7`). If A emits different IDs, edges rebuild cheaply
(rerun `graph_build.py`); resolution-by-label is ID-agnostic so accuracy carries.
**Ask A to confirm its ID scheme** so C/D can join on stable IDs.

## Next round (focus + I/O)
- **Swap to A's real `a_nodes`**; rerun edges + invariants on machine-extracted
  nodes — where violations should finally appear.
- **Add `references`/`referenced_by` as real edges** in `b_node_edges` (round 1
  kept refs only in `b_references`) → enables bounded graph-expansion for C/D.
- **Widen to Ch1 §1–§3** (round 1 went deep on §7) for the `1.x` grammar.
- **Owe to C:** a stable resolved-reference table to walk for graph-expansion
  retrieval. **Need from A:** confirmed node-ID scheme + full env recall (no
  dropped Corollaries).

## Recommendation (1 paragraph)
On Tu's §7, the document graph + §10 invariants + cross-reference resolution are
**feasible, fast (~1 s), free (no LLM), and high-quality** — 100% in-slice
reference accuracy with correct declining of out-of-slice targets, all six
round-1 edge types fully deterministic, and all seven invariants demonstrably
live. The structure layer is **not** where this spike's risk lives. The only
quality lever that matters is **upstream extraction recall** (Track A): the lone
round-1 failure was a node Track A-style extraction would have to recover (Cor
7.8), not a resolver weakness. Recommendation: **green-light the structured graph
for #50**, and spend Track A's budget on environment recall + Tu-grammar fidelity
(Problems vs bare numbering, unnumbered `Example.`), not on the graph/ref logic.

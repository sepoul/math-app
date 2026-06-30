# Track B — Document graph, references & validation — FINDINGS

Scope/contract: issue **#57** (Track B). Leads on **structure quality**.
Tables: `b_*` (consumes `a_*` or the seed fixture). Bucket: `track-b/`.

**Question:** from typed nodes, can we build the graph (`contains`/`parent_of`/
`next`/`previous`/`proven_by`/`has_equation`/`references`), enforce the §10
invariants, and resolve in-text cross-references ("by Theorem 4.7", "Problem
2.16") to node IDs?

Slice: **Tu, Ch1 §1–§3 + Ch7 §7 "Quotients"**. Branch: `spike/graph-grounding`.

---

# ROUND 2 — graph & grounding on the REAL corpus (Track A's `a_nodes`)

**R2 answer: the graph + grounding hold up on machine-extracted nodes.** Swapped
off the hand-seed to Track A's **159 `a_nodes`** (run `track-a-r1`). All edge
types reproduce cleanly; reference resolution is **100% on decidable refs** once
the Tu Problem/Exercise alias is handled; structural invariants are **clean** on
A's output (a *trustworthy* clean, after I fixed a Track-B sort bug the machine
data exposed); the only residual misses are **8 Track-A recall gaps**, all
verified real in the book.

## DID (R2)
1. **Swapped to `a_nodes`** — `load_nodes()` auto-detected the populated table (no
   code change needed; the R1 seam held). Rebuilt all edges on 159 machine nodes.
2. **Reran the 7 §10 invariants on machine output** — found + fixed a Track-B
   false-positive (numbering check compared siblings in DB/`node_id` order, so
   `3.10` looked like it regressed before `3.1`). Now sorts by page reading order;
   re-verified all 7 still fire on perturbation.
3. **Reference resolution across the FULL slice** incl. Ch1 §1–§3 (`1.x/2.x/3.x`)
   — handled the **Problem↔Exercise alias** (Tu prose cites `Problem N.M`; A
   labels the node `Exercise N.M`) via a unified bare-number exercise index.
4. **Promoted resolved refs → real `b_node_edges`** as `references` /
   `referenced_by` (Track C's graph-expansion substrate).

## TABLES (row counts, R2)
| table | rows |
|---|---|
| `b_node_edges` | **1100** (1032 structural + 68 reference) |
| `b_references` | **95** |
| `b_validation_issues` | **6** (all `reference_recall_gap` — Track A signal) |

## QUALITY (R2)

### Edges by type (1100), reproduction on machine nodes
| edge_type | count | reproduces cleanly? |
|---|---|---|
| `has_equation` | 437 | ✅ all 437 target real `a_equations` rows (0 dangling) |
| `contains` / `parent_of` | 157 / 157 | ✅ from `parent_id` |
| `next` / `previous` | 128 / 128 | ✅ reading-order sibling chains |
| `proven_by` | 25 | ✅ all 25 proofs attach to a theorem-like node via `proves`; 0 orphan, 0 non-theorem target |
| `references` / `referenced_by` | 34 / 34 | ✅ NEW; 0 dangling endpoints |

**Edge integrity:** 0 non-equation edges with a dangling endpoint; 0
`has_equation` edges with a missing `a_equations` target. **`proven_by` is the
edge most at risk on machine output** (depends on A's `proves` + proof labels) —
it reproduced perfectly here: A labels proofs bare `"Proof"`, parents them under
the subsection, and sets `proves` to the proven node's id (e.g.
`book.sub1.2.proof8 → book.sub1.2.lemma7`). **My R1 `proven_by` direction +
`proves`-scheme assumption matched A's exactly.**

### Reference-resolution accuracy on REAL nodes (95 mentions)
| method | total | resolved | correct |
|---|---|---|---|
| `env` (Theorem/Prop/.../Definition N.M) | 77 | 77 | 77 |
| `problem_alias` (Problem N.M → Exercise N.M node) | 7 | 7 | 7 |
| `env_out_of_slice` (Corollary A.36, Example 5.7) | 2 | 0 | 2 (correctly declined) |
| `problem_out_of_slice` (Problem 19.12) | 1 | 0 | 1 (correctly declined) |
| `env_recall_gap` (in-slice, no node) | 8 | 0 | 0 (honest miss) |

- **Resolver accuracy on DECIDABLE refs (excl. A recall gaps): 87 / 87 = 100%.**
- Raw self-correct incl. gaps: 87/95 = 91.6% — the 8.4% deficit is **entirely
  Track A recall**, not resolver error.

### Invariant violations on machine output
- **0 structural violations** (numbering, proof-attachment, child-before-parent,
  printed-page monotonicity, TOC coverage, header-as-heading). After fixing the
  numbering sort bug this is a **trustworthy** clean — A's extraction of the
  slice is structurally sound. Perturbation harness re-confirms all 7 fire.
- **6 `reference_recall_gap` warnings** logged for D's §17 attribution: in-slice
  items cited in prose but with **no extracted node** —
  `Exercise 3.13/3.15/3.17/3.20/3.22` (inline exercises in §3 prose) and
  `Exercise 7.11` (cited 3×). **All 6 verified to exist in the PDF** ⇒ genuine
  Track-A recall gaps (A got the end-of-section Problems block but missed inline
  `Exercise N.M (Title).*` items), not Track-B phantoms.

## WHAT TRACK C SHOULD WALK (the graph-expansion contract)
All in `book_rag_spike.b_node_edges` (cols: `from_node_id`, `to_node_id`,
`edge_type`, `confidence`, `evidence`). Endpoints are **Track A `a_nodes.node_id`**
(except `has_equation.to_node_id` = `a_equations.eq_id`). For bounded expansion:
- **`references` / `referenced_by`** — explicit in-text cross-refs (the new R2
  edges). Walk `references` out of a node for "what it cites"; `referenced_by`
  for "who cites this" (e.g. "which proofs cite this lemma").
- **`proven_by`** — node → its proof (theorem→proof direction).
- **`contains` / `parent_of`** — enclosing section / children.
- **`next` / `previous`** — local neighborhood within a parent.
- **`has_equation`** — node → equation id (join `a_equations`).
All edges carry `confidence`; bound expansion by depth + confidence per spec §14.

## Coordination with A (seam status, R2)
- **`a_nodes` populated** (159 rows, run `track-a-r1`) — auto-swap worked.
- **ID grammar (actual):** `book.sec<N>`, `book.sub<S>.<SS>`,
  `book.sub<S>.<SS>.<kind><n>` (e.g. `book.sub7.5.theorem117`,
  `book.sub1.2.proof8`). NB: the coordinator relayed `book.ch2.s7.*`; the real
  scheme in the DB is `book.sub7.*`. I adopted **what's in the DB**. §7 is indeed
  under **Chapter 2** (`book.sec7.parent_id = book.ch2`) — my R1 `book.ch1.s7`
  guess was wrong; now moot (I read A's ids).
- **`proves` scheme matched** my R1 assumption — no rework.
- **Ask A:** extract the **inline `Exercise N.M`** items (the 6 recall gaps), not
  just the end-of-section Problems block.

## BLOCKERS / NEXT (R2)
- **No blockers.** Live corpus churn observed (A wrote 143→160 nodes mid-round);
  the pipeline is idempotent (`truncate` + rebuild) so a re-run picks up A's
  latest. Re-run `track-b/graph_build.py` after A's next write.
- **NEXT round:** (a) add **bounded graph-expansion helper** (depth+confidence)
  on top of the edge set so C/D can call it directly; (b) close the loop on
  recall gaps once A re-extracts; (c) optionally add evidence-scored semantic
  edges (`uses`/`depends_on`) per spec §11 if D's queries need them.

---

# ROUND 1 (historical — hand-seed bootstrap)

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

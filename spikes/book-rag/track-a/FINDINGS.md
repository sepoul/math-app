# Track A — Structural extraction & the book skeleton — FINDINGS

Scope/contract: issue **#57** (Track A). Leads on **feasibility**. Owns
`_shared/schema.py`. Tables: `a_*`. Bucket: `track-a/`.

**Question:** can we deterministically turn Tu's PDF into the typed skeleton
(hierarchy + formal environments + page mapping + per-decision confidence),
leaning on the 269-entry outline — and where does determinism break?

**Round-1 verdict: YES for structure, NO for math.** A purely deterministic,
typography-driven parser recovers Tu's full skeleton for the slice at
**100% recall / 100% precision** on formal environments (113/113), with correct
hierarchy, page mapping, and proof->theorem linkage — in **~0.7 s** for 45 pages
(**~7 s projected for the whole 430-page book**, no model calls). The *only*
place determinism breaks is **display-math regions**: equations extract as
fragmented, out-of-order glyph-runs that no per-line rule can regroup or turn
into LaTeX. We treat them as first-class regions with raw evidence + low
confidence and leave LaTeX/regrouping to a later (model/OCR) pass — exactly as
the spec prescribes.

Pipeline: `track-a/extract.py` (one-pass, layout+typography). Tu-specific config
isolated in `track-a/tu_config.py`. Fidelity harness: `track-a/verify.py`
(independent typography GT vs. persisted `a_nodes`).

---

## The slice, located via the outline

`fitz.get_toc(simple=False)` returns Tu's **269-entry outline**, cleanly nested
**L1=Chapter / L2=section / L3=Subsection|Problems**. Slice -> 1-based PDF pages:

| slice part | outline | pdf pages | printed |
|---|---|---|---|
| Ch1 section1 Smooth Functions | L2 @ pdf 22 | 22-28 | 3-9 |
| Ch1 section2 Tangent Vectors as Derivations | L2 @ pdf 29 | 29-36 | 10-17 |
| Ch1 section3 Exterior Algebra of Multicovectors | L2 @ pdf 37 | 37-52 | 18-33 |
| **section7 Quotients** | L2 @ pdf 90 | 90-103 | 71-84 |

> **Gotcha that bites the spec's mental model:** "Ch7 section7 Quotients" in the
> issue shorthand is **section 7**, the 7th section under Tu's *continuous,
> book-wide* section numbering — and **section 7 lives inside Chapter 2
> (Manifolds)**, not a "Chapter 7". The extractor takes the parent chapter from
> the **outline** (`book.ch2`), not from the last in-body chapter opener, and
> **synthesizes** the `book.ch2` node (its opener page 66 is outside the slice).
> 0 dangling `parent_id`s result.

---

## Feasibility

- **Hierarchy (chapter/section/subsection): 100%.** 2 chapters (1 in-body +
  1 synthesized), 4/4 sections (section 1,2,3,7), 24/24 subsections — all with
  correct title, parent, page-span, and `heading_path`. Validated against the
  outline (every in-body heading matched an outline entry; titles back-filled
  from the outline where the in-body title span was weak).
- **Formal environments: 100% recall / 100% precision** (113/113 located) for
  def / thm / prop / lemma / cor / proof / example / remark / exercise. See
  scorecard.
- **Proof->theorem linkage: 25/25** proofs attached to the correct preceding
  theorem-like item via the `proves` field (hand-checked: e.g. proof@p95 ->
  Theorem 7.9, proof@p32 -> Theorem 2.2). 0 orphans in the slice.
- **Page mapping (pdf<->printed): 44/45 pages.** The printed number is read
  **per-page from the running header** (NOT a constant offset). In the slice the
  offset is a clean **+19** (pdf 22 -> printed 3 ... pdf 102 -> printed 83); 1
  page (pdf 103, the tail of section 7 Problems) has no extractable margin number.
- **Where determinism breaks -> math** (below). Everything *structural* is
  deterministic and high-confidence; no model help needed for the skeleton.

### The Tu-specific parser config (correcting the generic spec regex)

The spec's generic `section: ^(\d+)\.(\d+)` is **wrong for Tu** and would mis-tag
every subsection as a section. Corrected config (`tu_config.py`), keyed on
**typography**, not regex alone:

| element | Tu pattern | font / size signature |
|---|---|---|
| chapter | `Chapter K` (+ outline title) | Times-Bold ~14.3 |
| **section** | **`<sec>N Title`** (continuous, book-wide N) | Times-Bold ~14.3 |
| **subsection** | **`N.M Title`** (N tracks the *section*) | Times-Bold 12.0 |
| def / thm / prop / lemma / cor | `Keyword N.M.` | **Times-Bold 10** |
| proof / example / remark | `Keyword [N.M].` | **Times-Italic 10** |
| **exercise** | `N.M. Title` under a **`Problems`** block | **Times-Bold 9** |
| body | — | Times-Roman 10 |
| running header | printed-page + section title | Times 8-9 @ stable y~=27.7 |

Heading vs. environment vs. exercise are separated by **(bold/italic, size)**,
disambiguated from each other and from figure captions (`Fig. N.M.`, also
bold-9) and the `Problems` header (bold-12, same size as a subsection -> matched
by the literal word).

---

## Quality (fidelity scorecard)

Ground truth = independent typography scan of the slice (`verify.py`,
hand-validated against the raw label lines), deduped to unique items. "Located"
= same (kind, page) present in both GT and persisted `a_nodes`.

| element | in slice (truth) | recovered | correctly located | notes |
|---|---|---|---|---|
| section | 4 | 4 | 4 | section 1,2,3,7; section7 -> Ch2 from outline |
| subsection | 24 | 24 | 24 | titles back-filled from outline |
| definition | 5 | 5 | 5 | incl. unnumbered-style "Definition 2.5." |
| theorem | 3 | 3 | 3 | 2.2, 7.7, 7.9 |
| proposition | 13 | 13 | 13 | |
| lemma | 6 | 6 | 6 | |
| corollary | 8 | 8 | 8 | |
| proof | 25 | 25 | 25 | all linked via `proves` |
| example | 19 | 19 | 19 | incl. 4 *unnumbered* "Example." |
| remark | 2 | 2 | 2 | both unnumbered |
| exercise | 32 | 32 | 32 | under `Problems`, `N.M.` labels |
| **TOTAL** | **113** | **113** | **113** | **recall 100% / precision 100%** |

**Confidence distribution:** 142/143 nodes @ confidence 1.0 (clean
typography + outline match), 1 @ 0.9 (the synthesized `book.ch2`). No node landed
in a review-queue band — for *this slice* the structure is unambiguous.

> **Honest caveat on the 100/100.** This number measures **label-line detection
> + location** (does the typography rule fire on exactly the real labels). That
> is genuinely strong because Tu's typography is clean and separable — but GT and
> extractor share detection logic, so it is *not* an independent oracle. What it
> does **not** measure, and what a human reviewer should still spot-check:
> **node text-boundary correctness** (spot-checked OK: Definition 1.1 and Theorem
> 7.9 statements end exactly before the next item) and **math** (below, where it
> genuinely breaks).

### Where pure determinism breaks / where model help is needed

1. **Display-math reading order & regrouping (the real break).** Tu's math is
   text-as-glyphs in CM/Symbol/MSBM fonts, but a single displayed equation comes
   out as **many fragments on shifted baselines** (numerators, sub/superscripts,
   sum/integral bounds) in **scrambled order** — e.g. Taylor's formula on pdf 25
   splits into `f(x) = f(p)+`, `(xi - pi)gi(x),`, `df`, `dxi (p).`, `i=1` as
   separate "lines." Per-line extraction **cannot** reconstruct the equation or
   its order. We flag fragments (math-font ratio >= 0.45, or indented x0 >= 90
   with ratio >= 0.20) -> **584 `a_equations` rows** with `raw_text` +
   `latex=NULL` + `latex_confidence=0.2`, each linked to its parent node;
   **27 page-region crops** uploaded to `track-a/eq/*.png` as visual evidence.
   **Regrouping fragments into ordered regions and producing LaTeX needs a
   model/OCR pass** (2D bbox clustering + vision). The 584 over-counts true
   display equations (one equation = several fragment rows); a true
   display-equation count needs the regrouping step we deliberately deferred.
2. **Labels at a page top.** A theorem/exercise label can open a page at
   **y~=47**, *just below* the running header at y~=27.7. A naive "drop y<60 as
   header" filter **eats real body labels** (this cost us Theorem 7.9, Prop 3.12,
   Lemma 3.11, Exercises 3.4/7.7 until fixed). Fix: header = **tight y-band
   (<35) AND small font (<9.5pt)** — the two-part test is load-bearing. Risk for
   the full book: any page whose first body line creeps above y~=35.
3. **Proof boundaries / attachment.** Deterministic here (proof attaches to the
   immediately-preceding theorem-like node) and 25/25 correct in-slice — but this
   is a *heuristic*; a proof with no preceding theorem-like item (or one
   separated by an intervening example) would mis-attach. Confidence is lowered
   to 0.6 + flagged when no antecedent exists. Across the whole book this is the
   most likely structural error source after math.

---

## Speed / cost

- **Extraction: ~0.7 s for the 45-page slice** (~15 ms/page), **pure-Python /
  PyMuPDF, zero model calls, zero network** (DB write + 27 crop uploads are
  separate I/O). **Projected ~7 s for the full 430-page book.**
- **$ cost: $0** for the deterministic skeleton. Cost only appears if/when the
  deferred math-regrouping/LaTeX pass calls a vision model on equation crops.
- Cheap enough to run inside a daily synthesis pass many times over.

---

## Schema

**`_shared/schema.py` UNCHANGED** (verified `git diff` empty). The existing
`Node` / `Edge` / `Span` / `Block` / `TocEntry` / `Equation` shapes were
sufficient. **B/C/D: no contract change to absorb this round.** Fields exercised:
`Node.{proves, math_region_ids, heading_path, page_*_start/end, confidence,
evidence}`, `Equation.{raw_text, latex(NULL), latex_confidence, image_crop_key,
parent_node_id}`. If a future round adds fragment-regrouping it may want an
`Equation.region_id` / `fragment_order`; will announce additively before adding.

## Tables written (run_id `track-a-r1`)

| table | rows |
|---|---|
| a_parse_runs | 1 |
| a_pages | 45 (44 with printed-page) |
| a_spans | 19 734 |
| a_blocks | 2 158 (one per content line) |
| a_toc_entries | 269 (full outline; 33 in slice) |
| a_nodes | 143 (2 chapter, 4 section, 24 subsection, 113 environments) |
| a_equations | 584 (27 with crop in bucket `track-a/eq/`) |

Integrity: 0 dangling `parent_id`, 0 nodes missing `heading_path`, 584/584
equations parented.

## Seed fixture (task-zero deliverable, now backed by real data)

`seed/seed_nodes.json` (11 nodes: section7 + 2 subsections + Def 7.5 + Prop
7.1/7.3 + their proofs + Example 7.2 + Exercise 7.1) and `seed/seed_edges.json`
(8 edges: `contains` + `proven_by`), conforming to `_shared/schema.py`. Lets
B/C/D run against a realistic section-7 sub-tree without depending on a live
extractor run.

## Recommendation (1 paragraph)

For Tu, the typed **skeleton is a solved, deterministic, ~7-s/$0 problem** — the
269-entry outline + clean separable typography give chapter/section/subsection,
all nine formal-environment kinds, printed-page mapping, and proof->theorem
linkage at full recall with high confidence, with no model in the loop. Build
#50's book skeleton on a **book-specific config** (per spec section 16, the
correct engineering choice) like `tu_config.py`, validated against the outline,
with a review queue keyed on the three known break points (math regions,
page-top labels, proof attachment). The **one hard part is math**: equations
must be first-class regions carrying raw evidence + a crop + low LaTeX
confidence, with fragment-regrouping/LaTeX explicitly deferred to a later
model/OCR pass — do **not** block the skeleton (or retrieval) on perfect math,
and do **not** trust equation row counts as equation counts until regrouping
exists.

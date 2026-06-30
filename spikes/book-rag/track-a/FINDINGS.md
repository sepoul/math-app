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

---

# ROUND 2 — hardening the canonical corpus (#57)

R1 left three gaps that B/C/D now depend on; all three are closed. Code:
`track-a/harden.py` (regroup + vision + inline-defs + aliases + out-of-slice
validation). The R1 labeled-environment scorecard is **unchanged: 113/113,
100%/100%** (re-verified; `verify.py` now scopes to labeled envs, excluding the
new inline defs).

## Gap 1 — MATH REGROUPING + vision->LaTeX (R1's "one real break")

**True equation count: 205 ordered regions, NOT 584.** Deterministic 2D bbox
clustering (`regroup_equations`): fragments sorted by (y, x); a new region
starts when the vertical gap exceeds 16pt; members ordered top-row then
left-to-right (row tolerance 6pt). 584 raw fragments -> **205 display-equation
regions** (avg 2.85 fragments/region) in **~1 s**, $0. Persisted to the new
`a_eq_regions` table; raw `a_equations` fragments are **never overwritten**
(`member_eq_ids` links each region back to its fragments + `ordered_text` joins
them in reading order).

**Vision->LaTeX accuracy (Claude `claude-opus-4-8`, one image call per region
crop):** on a 10-region sample (the densest, hardest multi-fragment regions):

| region (page) | frags | conf | recovered LaTeX (head) |
|---|---|---|---|
| p23 (Taylor) | 12 | 0.97 | `f(x) = f(p) + \sum_i \frac{\partial f}{\partial x^i}(p)(x^i ...` |
| p100 (RP^n charts) | 14 | 0.97 | `y^1 = \frac{1}{x^1},\ y^2 = \frac{x^2}{x^1}, ...` |
| p33 (vector field) | 9 | 0.95 | `X = \frac{-y}{\sqrt{x^2+y^2}} \frac{\partial}{\partial x} + ...` |
| p49 (wedge) | 11 | 0.97 | `(\alpha^1 \wedge \cdots \wedge \alpha^k)(v_1, ...` |
| p99 (RP^n chart map) | 9 | **0.85** | `[a^0,\ldots,a^n] \xrightarrow{\phi_0} ...` (hard multi-line map) |

**9/10 at conf 0.95-0.97; 1/10 at 0.85** (the model's own faithfulness flag).
**Mean latex_confidence ~0.95.** The reconstructions are genuinely faithful
(sub/superscripts, fractions, sums/integrals, `\wedge`, `aligned` blocks). Stored
as `latex` + `latex_confidence` on `a_eq_regions`, **raw evidence kept** (per spec
§9 "never silently replace source evidence"). Region crops -> bucket
`track-a/eqregion/*.png`. **Verdict: math IS recoverable** — deterministic
regroup for the count/structure, one cheap vision call per region for LaTeX. The
584 figure was a ~2.85x over-count; **205 is the number B/C/D should use.**

## Gap 2 — INLINE DEFINITIONS (Track C found 0 `Definition N.M` labels)

Tu defines most terms NOT with a labeled environment but by **italicizing the
term in prose** (LaTeX `\emph`), after a definitional trigger ("is called", "are
called", "is a/an", "we call", "defined as"...). `detect_inline_defs` finds the
trigger + the Times-Italic-10 term, filters statement-glue stopwords,
hyphenation breaks, and mid-phrase fragments. **16 definitional terms recovered**
in the slice, parented to their subsection, emitted as `kind='definition'`
(`book.inlinedef.N`, confidence 0.7): tangent vectors, equivalence, linear map,
multicovectors, dual space V, covectors, k-tensor, exterior product, exterior
algebra, quotient topology, quotient space, standard atlas, cycle of length r,
identification, left action, superscripts. **~13/16 are clean math definienda;
~3 are borderline** (e.g. "superscripts", "left action") — the trigger heuristic
is high-recall / moderate-precision; a model pass could rank these. This gives
"define X" queries a real target where the labeled-definition count (5) was
near-empty. The slice now has **21 definition nodes (5 labeled + 16 inline)**.

## Gap 3 — CONTRACTS for B/D

**PROOF-NODE SCHEME (authoritative):**
- **id pattern:** `<parent_node_id>.proof<seq>` where `seq` is a global node
  index at creation, e.g. `book.sub1.2.proof8`. Proofs are **separate nodes**,
  `kind='proof'`, `label="Proof"`.
- **linkage:** the proof's `proves` field = the `node_id` of the immediately
  preceding theorem-like item (theorem/proposition/lemma/corollary/definition).
  25/25 proofs in the slice are linked.
- **resolving "Proof of Theorem 7.7" -> a proof node:** resolve "Theorem 7.7" to
  its node_id (via label/alias), then find the proof node whose `proves` equals
  that node_id. Equivalently, the proof node carries the alias `"Proof of
  Theorem 7.7"` directly (see below).

**ALIASES (new `a_nodes.aliases text[]` column; 159 nodes populated):** every
node carries the textual forms B's resolver and D's gold need to match:
- numbered envs: `["Theorem 7.7", "7.7", "Thm 7.7"]`; exercises also get
  `"Problem N.M"` (Tu's in-text name) + the exercise title — e.g.
  `book...exercise138` (Exercise 7.6): `["Exercise 7.6","7.6","Problem 7.6",
  "Quotient of R by 2πZ"]`.
- proofs: `["Proof", "Proof of Lemma 1.4", "proof of 1.4"]` derived from the
  proven node — e.g. `book.sub1.2.proof8`.
- sections/definitions also carry their title as an alias.

## Out-of-slice validation of the header / page-top rule (de-risks full book)

The `y<HEADER_BAND_Y(35) AND size<9.5pt` two-part header rule, tested on 5
**out-of-slice** pages (pdf 120/180/250/300/370, NOT indexed): **5/5 OK** — the
first body line was correctly NOT eaten as header in every case, including a body
`Theorem D.3` label opening pdf 370 at y=48.6/10pt, a chapter `§25` heading at
y=69.8/14.3pt (pdf 300), and a `Problems` header at y=47/12pt (pdf 180). Printed
page numbers extracted on all 5. The rule generalizes; the residual risk
remains any page whose first body line creeps above y~35 (none seen).

## Schema changes (ADDITIVE — B/C/D please note)

Announced loudly: **two additive changes**, both in `_shared/schema.py` AND
`_shared/provision.py` (idempotent DDL):
1. **new table `a_eq_regions`** — regrouped ordered display-equation regions
   (`region_id, pdf_page, bbox, member_eq_ids[], ordered_text, latex,
   latex_confidence, image_crop_key, parent_node_id, n_fragments`). New pydantic
   model `EqRegion`. Raw `a_equations` unchanged.
2. **new column `a_nodes.aliases text[]`** — textual aliases (above). New
   `Node.aliases` field. Existing fields/rows unchanged; no breaking change.

## Tables written (run_id `track-a-r1`, after R2)

| table | rows | note |
|---|---|---|
| a_nodes | 159 | 143 R1 + 16 inline defs; 159 with `aliases` |
| a_equations | 584 | raw fragments, **unchanged** |
| a_eq_regions | 205 | **new**; 10 with vision LaTeX + crop |
| (a_pages / a_spans / a_blocks / a_toc_entries / a_parse_runs) | unchanged | |

## R2 recommendation (1 paragraph)

All three downstream gaps are closed deterministically + cheaply. **Equations:
the real count is 205 regions (regroup is deterministic, ~1s/$0); LaTeX is
recoverable at ~0.95 confidence via one Opus vision call per region** — for #50,
regroup everything, then vision only the regions a query actually retrieves
(lazy, cost-bounded). **Inline definitions are essential for Tu** (labeled
definitions are rare; the real definitional surface is italic-in-prose) — ship
the trigger+italic detector with a model re-rank to lift precision past the
current ~80%. **Contracts:** B should resolve references via `aliases` (exact
+ `Problem N.M` + "Proof of …" forms) and the `proves` linkage; D's gold should
key on the same aliases. The header/page-top rule generalizes off-slice, so
scaling to 430 pages is low-risk on the structural side.

---

# ROUND 3 — close recall gaps + FREEZE the corpus (#57)

Lighter round: close the 6 verified recall gaps, freeze the corpus for C/D
scoring, complete the speed/cost ledger. No further mid-round churn after this.

## Gap closure — inline exercises (full recall)

**Root cause:** R1/R2 only flagged bold-9 exercises *inside* the end-of-section
`Problems` block (bare `N.M.` form). Tu ALSO interleaves exercises in the body
prose with the explicit keyword form **`Exercise N.M (Title)`** (still Times-Bold
9pt). Added `INLINE_EXERCISE_RE` + a non-`in_problems`-gated branch in
`classify_env` (keyword `Exercise` + bold-9 is the discriminator).

**Recovered the 6 B-verified gaps + 1 more I'd also missed:**
`Exercise 3.13, 3.15, 3.17, 3.20, 3.22` (Ch1 §3, pdf 44–47), `Exercise 7.11`
(§7, pdf 96), **and `Exercise 3.6 (Inversions)` (pdf 40)** — exercises **32 → 39**.

**Numbering-collision finding (flag for B's resolver):** Tu reuses the number
**3.6 for two distinct exercises** — inline `Exercise 3.6 (Inversions)` @pdf 40
AND `3.6 Wedge product and scalars` in the §3 Problems block @pdf 52. Both are
real, both extracted (distinct node_ids, shared `label="Exercise 3.6"`). B's
reference resolver must disambiguate `Exercise 3.6` by page/context, not assume
label-uniqueness. (`verify.py` GT now keys exercises by (kind, num, page) to
count both.)

**Fidelity scorecard — FULL RECALL, re-verified:**

| element | truth | recovered | located |
|---|---|---|---|
| section / subsection | 4 / 24 | 4 / 24 | 4 / 24 |
| definition (labeled) | 5 | 5 | 5 |
| theorem / proposition / lemma / corollary | 3 / 13 / 6 / 8 | = | = |
| proof | 25 | 25 | 25 (all linked) |
| example / remark | 19 / 2 | = | = |
| **exercise** | **39** | **39** | **39** |
| **TOTAL (labeled envs)** | **120** | **120** | **120** |

**recall 100% / precision 100%** on labeled formal environments.

## FROZEN corpus (FINAL for R3 scoring)

- **run_id: `track-a-r1`** (stable across all rounds — this is the canonical id).
- **`a_nodes`: 166 total** — 2 chapter, 4 section, 24 subsection, 5 labeled
  definition + 16 inline definition (=21 definition), 39 exercise, 25 proof, 19
  example, 13 proposition, 8 corollary, 6 lemma, 3 theorem, 2 remark. **166/166
  carry `aliases`.**
- **`a_eq_regions`: 205** ordered display-equation regions (10 with vision LaTeX
  @ conf 0.95–0.98); `a_equations`: 584 raw fragments (unchanged).
- **Commitment: no further structural/content churn this round.** C and D can
  score against `track-a-r1` as a stable foundation.

## Speed / cost ledger (for D)

Recorded authoritatively in **`a_parse_runs.notes`** (Track A's zone) AND mirrored
into **`d_speed_cost`** (additive insert-only, `stage='extraction'`,
`run_label='track-a-extraction'`, tagged `author=track-a`; D's 310 existing rows
untouched, 310→312):

| metric | value |
|---|---|
| slice extraction (45 pp), best-of-3 | **0.68 s** (15.1 ms/page) |
| full-book projection (430 pp) | **~6.49 s** |
| model calls / cost (deterministic extraction) | **0 / $0** |

Vision→LaTeX is a **separate optional per-region pass** (one Opus image call per
region, ~0.95 confidence) — priced per region, not part of the 6.49 s figure;
run it lazily only on retrieved regions for #50.

## R3 recommendation (1 paragraph)

The structural substrate is **done and frozen**: full recall (120/120 labeled
envs, 100%/100%), 166 typed nodes with aliases, 205 ordered equation regions,
deterministic extraction at ~6.5 s / $0 for the whole book. The one residual the
graph layer must handle is **label collisions** (Exercise 3.6 ×2) — resolve by
page/context. C/D have a stable `track-a-r1` corpus + a complete speed ledger to
produce the go/no-go verdict.

# Track B — Document graph, references & validation — FINDINGS

Scope/contract: issue **#57** (Track B). Leads on **structure quality**.
Tables: `b_*` (consumes `a_*` or the seed fixture). Bucket: `track-b/`.

**Question:** from typed nodes, can we build the graph (`contains`/`parent_of`/
`next`/`previous`/`proven_by`/`has_equation`/`references`), enforce the §10
invariants, and resolve in-text cross-references ("by Theorem 4.7", "Problem
2.16") to node IDs?

Slice: **Tu, Ch1 §1–§3 + Ch7 §7 "Quotients"**. Branch: `spike/graph-grounding`.

---

# ROUND 4 (FINAL) — the §11 semantic-edge experiment: `depends_on` lift vs noise

**R4 answer / RECOMMENDATION: ship the deterministic tier for #50; add the
`depends_on` semantic tier only behind a `dependencies`/`expansion` intent gate —
it is a SMALL, SAFE, OPTIONAL win, not a foundation.** Evidence-backed
`depends_on` edges lift graph-expansion recall **+5.6% (83.3%→88.9%, +1 true gold
node)** with **0 false bridges** (every edge audited true), but the lift is narrow
(1 of 3 misses) and the other 2 misses are unrecoverable without speculation.

## DID (R4)
1. **`track-b/semantic_edges.py`** — derives `depends_on` from **defensible
   signals only**: (1) proof-cited results ("Apply Corollary 7.10" → dep on Cor
   7.10, conf 0.9), (2) statement "by/using <Label>" (conf 0.8; **0 in this
   slice** — Tu keeps dependency language in proofs). Emits BOTH directions
   (`depends_on` / `depended_on_by`, like references/referenced_by). **No
   term-overlap / topical bridges** (a false bridge is worse than a miss — #53).
2. **`track-b/depends_on_experiment.py`** — A/B over all 5 gold queries:
   deterministic-only vs +semantic, measuring LIFT and NOISE (distinct nodes).
3. Wired `depends_on`/`depended_on_by` into the `expansion` intent + added a
   `dependencies` intent and an `expansion_deterministic` control.

## THE EXPERIMENT (lift vs noise, quantified)
| query | seed | det-recall | +depends_on | lift | extra distinct nodes (gold / non-gold) |
|---|---|---|---|---|---|
| D-017 | Thm 7.7 | 1/1 100% | 1/1 100% | 0 | 4 (0 / 4) |
| D-020 | sub7.6 | 3/3 100% | 3/3 100% | 0 | 0 |
| D-022 | §3 | 5/5 100% | 5/5 100% | 0 | 0 |
| **D-023** | Thm 7.9 | 3/5 60% | **4/5 80%** | **+1** | 1 (**1** / 0) |
| D-026 | Thm 7.7 | 3/4 75% | 3/4 75% | 0 | 4 (0 / 4) |
| **TOTAL** | | **15/18 83.3%** | **16/18 88.9%** | **+1 (+5.6%)** | 8 non-gold |

### LIFT — the win
**D-023 recovers Corollary 7.15** via `Thm 7.9 →next→ Cor 7.10 ←depended_on_by←
Cor 7.15` (d2, score 0.855). This is exactly the bridge R3 lacked: Cor 7.15's
proof says **"Apply Corollary 7.10"**, so the dependency is author-stated, not
inferred.

### NOISE — what it actually is (NOT false bridges)
The "8 non-gold neighbors" reduce to **1 true semantic neighbor + its structural
fan-out**: on a Theorem-7.7 seed, `depended_on_by` reaches **Prop 7.16** (whose
proof literally cites Theorem 7.7 — a TRUE dependency), and depth-2 then pulls
Prop 7.16's own `next`/`proven_by`/`previous` neighbors (Cor 7.15, 2 proofs).
**False-bridge audit: 0 / 11 edges mismatched** — every `depends_on` is backed by
a real cited label. So the cost is **precision against a deliberately tight gold**
(D didn't list Prop 7.16 for D-026), not wrong edges, and it is **bounded** (one
hop into one neighbor subsection).

### The 2 misses depends_on can NOT fix (and shouldn't try)
- **Prop 7.14** (D-023): its proof proves openness from first principles, citing
  **no labeled result** → no evidence-backed edge exists.
- **Prop 7.4** (D-026): no proof, cites nothing → no anchor.
Both are connected to the cluster only by *conceptual* adjacency ("open
equivalence relation"). Bridging them needs term-overlap inference = exactly the
speculative edge that risks false positives. **We correctly leave them as misses.**

## COST / BENEFIT CALL FOR #50 / #53
| | deterministic tier | + `depends_on` tier |
|---|---|---|
| structural-query recall | 100% | 100% (unchanged) |
| expansion-query recall | 83.3% | 88.9% (**+5.6%**) |
| false bridges | 0 | **0** (all proof-cited, audited) |
| precision cost | — | +1 true-but-not-gold neighbor on Thm-seeded expansion |
| build cost | regex over proof text | same pass, +~0 ms, $0 |

**Verdict:** the deterministic tier is the **right foundation** (it alone hits
100% structural, 83% expansion, free, deterministic). `depends_on` is a **cheap,
zero-false-bridge, optional enhancement** worth **only +5.6%** and only for
`expansion`/`dependencies` intents. **Recommend: build deterministic for #50;
include `depends_on` behind the intent gate (it never fires on structural/direct
intents, so it can't regress them); do NOT pursue term-overlap semantic edges**
— the remaining misses aren't worth the false-bridge risk (#53's exact warning).

## FINAL GRAPH STATS (frozen 166-node corpus)
| table | rows |
|---|---|
| `b_node_edges` | **1160** |
| `b_references` | **96** (96/96 = 100% correct, **0 recall gaps**) |
| `b_validation_issues` | **0** |

Edges: has_equation 441, contains/parent_of 164 each, next/previous 135 each,
references/referenced_by 37 each, proven_by 25, **depends_on 11 + depended_on_by
11 (the §11 semantic tier)**. **0 dangling endpoints** across all 1160 edges.

## FINAL RECOMMENDATION (Track B, whole spike)
Structured retrieval over Tu's graph is **feasible, fast (~1 s), free (no LLM),
and high-quality**: deterministic structure recovers 100% of structural gold and
100% of in-slice references (after A's recall closure), with all §10 invariants
clean and live. The graph is a **first-class, intent-gated answer-path** C can
walk (bounded `expand()` helper). The §11 semantic tier earns a **conditional
yes**: a safe +5.6% on expansion queries with zero false bridges, gated by intent.
**Track B's slice of the go/no-go is GO** — the structure layer is the reliable
part of this pipeline; the residual risk lives upstream (extraction recall, now
closed for the slice) and in conceptual-dependency edges we deliberately don't
build.

---

# ROUND 3 — the graph as C's structural answer-path (§10–11 → §12–15)

**R3 answer: the graph is now a first-class, intent-gated retrieval path with a
bounded expansion helper C imports directly.** On A's **frozen 150-node corpus**
reference resolution hit **96/96 = 100% with ZERO recall gaps** (all 6 R2 gaps
closed by A). The helper recovers **100% of structural gold** (D-017/020/022) and
**60–75% of graph-expansion gold** (D-023/026) — the remainder are genuine
cross-subsection *semantic* dependencies no deterministic edge captures (quantifies
the value of spec-§11 `depends_on`).

## DID (R3)
1. **Shipped `track-b/expand.py`** — a bounded, explainable expansion helper C
   calls directly (signature below). Intent-gated + depth/confidence-capped (§14),
   directly fixing R2's −0.067 recall regression from *global* neighbor injection.
2. **Re-ran on A's frozen corpus** (A re-extracted 159→**150** nodes mid-round,
   closing the 6 recall gaps + renumbering IDs). Edges live + current; pipeline is
   idempotent so it picked up the freeze on re-run.
3. **Re-resolved references** — **96/96 = 100%**, **0 recall gaps** (was 8).
4. **Built `track-b/edge_gold_map.py`** — the exact edge→gold mapping for
   D-017/020/022/023/026 (deliverable #4), resilient to A's ID churn (seeds + gold
   resolved live by label/structural lookup, not hardcoded IDs).

## THE HELPER C WIRES IN (signature)
```python
from expand import expand, Neighbor, INTENT_EDGE_SETS   # track-b/expand.py
expand(seed_node_id: str,
       edge_types: Iterable[str] | None = None,   # explicit filter, OR:
       *, intent: str | None = None,              # INTENT_EDGE_SETS key (gates edges)
       depth: int = 1, min_confidence: float = 0.5,
       limit: int | None = None) -> list[Neighbor]
# Neighbor(node_id, depth, via_edge, score, path)  — score = Π edge-conf along path;
# path = [seed,...,node] is the EXPLANATION. Best-first; bounded; acyclic.
```
`INTENT_EDGE_SETS` (C maps `d_queries.intent` → key):
`structural_neighbor`→{next,previous} d1 · `structural_contains`→{contains} d1 ·
`proof`→{proven_by} d1 · `references`→{references,referenced_by} d2 ·
`expansion`→{proven_by,next,previous,references,contains} d2. C resolves the seed
(exact-label lexical hit) then calls `expand(seed, intent=...)`; returned node_ids
feed C's candidate set / rerank. **Endpoints are `a_nodes.node_id`** (has_equation →
`a_equations.eq_id`).

## TABLES (row counts, R3 — frozen 150-node corpus)
| table | rows |
|---|---|
| `b_node_edges` | **1076** (1002 structural + 74 reference) |
| `b_references` | **96** |
| `b_validation_issues` | **0** (recall gaps closed → no warnings) |

Edge mix: has_equation 441, contains/parent_of 148, next/previous 120,
references/referenced_by 37, proven_by 25.

## QUALITY (R3)
### Final reference accuracy on the FROZEN corpus
- **96 / 96 = 100% on decidable refs; 0 in-slice recall gaps** (R2 had 8). The 3
  remaining declines are correct out-of-slice (`Corollary A.36`, `Example 5.7`,
  `Problem 19.12`). **A's freeze closed every gap** (e.g. `Exercise 7.11` →
  `book.sub7.6.exercise130`, `Exercise 3.13` → `book.sub3.5.exercise62`).
- **0 structural invariant violations** on the frozen corpus.

### Helper recovery vs D's gold (bounded expansion)
| query | intent | edges that back the gold | gold recall |
|---|---|---|---|
| **D-017** | structural_neighbor | **`next`** (Thm 7.7 → Cor 7.8) | **1/1 = 100%** |
| **D-020** | structural_contains | **`contains`** (7.6 → Prop7.14/Cor7.15/Prop7.16) | **3/3 = 100%** |
| **D-022** | structural_contains | **`contains`** (§3 → sub 3.1–3.10) | **5/5 = 100%** |
| **D-023** | expansion | `next`+`references` (Cor7.10, Thm7.7) | 3/5 = 60% |
| **D-026** | expansion | `proven_by`+`next` (Proof, Cor7.8) | 3/4 = 75% |

### EDGE → GOLD mapping (what C targets, what D attributes)
- **D-017** Cor 7.8 ← `next` from Theorem 7.7 (d1).
- **D-020** Prop 7.14 / Cor 7.15 / Prop 7.16 ← `contains` from `book.sub7.6` (d1).
  *NB: D's intent text says "under 7.7" but A parents these under `book.sub7.6` —
  C must resolve the seed to A's actual subsection (7.6), not the literal "7.7".*
- **D-022** sub 3.1–3.10 ← `contains` from `book.sec3` (d1).
- **D-023** Cor 7.10 ← `next` (d1); Thm 7.7 ← `references` via the proof (d2).
  **Prop 7.14 + Cor 7.15 NOT reached** — they live in 7.6 and connect to the
  open-map result only by *mathematical dependency* (Cor 7.15 "applies the
  open-relation second-countability result"); no `next`/`contains`/`references`
  edge bridges 7.5→7.6. **Needs §11 `depends_on`.**
- **D-026** Proof ← `proven_by` (d1); Cor 7.8 ← `next` (d1). **Prop 7.4 NOT
  reached** — zero structural/reference edges touch it; pure semantic link.
  **Needs §11 `depends_on`.**

**Honest headline for the verdict:** deterministic structural edges fully answer
*structural* queries (label/contains/neighbor/proof = 100%) but cap
*graph-expansion* recall at 60–75% — the gap is exactly the **3 cross-subsection
semantic dependencies** (§11 `depends_on`/`uses`, explicitly "optional later" in
the spec). This is the precise, quantified cost of NOT building semantic edges.

## What C should do with this (the R2 fix)
Gate expansion by intent: only call `expand` for `structural_*` / `expansion` /
`proof` / `references` intents, and feed neighbors as **boosted candidates**, not
replacements. Do NOT expand on `direct`/`conceptual` intents (that injected the
R2 global-neighbor noise). Bound at depth ≤2, min_confidence 0.5.

## BLOCKERS / NEXT (R3)
- **No blockers.** Corpus is FROZEN at 150 nodes; edges + refs + mapping are live
  and consistent. Re-run `graph_build.py` only if A re-opens the freeze.
- **NEXT (R4):** add a **conservative, evidence-backed `depends_on` edge** (§11)
  to close the 3 expansion misses — derive from proof-cited results + shared
  defining-construction terms, confidence-scored — and re-measure D-023/026.
  Quantify the recall lift vs the noise risk so the control plane can decide if
  semantic edges earn their place in #50.

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

# Track C → Track D — the gold format Track C needs to score against (R2)

This is Track C's **conceptual coordination** of the gold contract (per the R1
task). Track D owns `d_queries` / `d_gold`; this records the shape C will consume
so D can publish it without a second round-trip. C will **not** invent its own
metrics — it scores against whatever D lands in these tables/files.

## What Track C joins on

C retrieves **chunks**, and each structured chunk carries a `node_id`
(`c_chunks.node_id`, e.g. `c.tu.sec7.theorem.theorem_7_7_1`) and a `label`
(e.g. `Theorem 7.7`). The naive baseline has **neither** — only `chunk_id` +
`page_pdf_start`. So gold must be expressible in a way that can be matched
against *both* index families. The cleanest join keys, in priority order:

1. **`gold_label`** — `"Theorem 7.7"`, `"Exercise 7.11"`, `"§7"`. Robust across
   sources; survives node-id scheme changes. **Preferred for direct/structural
   queries.**
2. **`gold_node_id`** — exact node id, when D wants to pin a specific unit. Note
   C's R1 fallback ids (`c.tu.secN.kind.label_n`) will be **replaced** by Track
   A's ids once `a_nodes` lands, so prefer `gold_label` where possible.
3. **`gold_page` (pdf page range)** — needed to score the **naive baseline**,
   which has no labels/ids. A baseline window is "correct" if its
   `page_pdf_start` falls inside (or within ±1 of) the gold node's pdf page
   range. **Please include a page range on every gold row** so C can score
   structured and naive on the same stick.

## Proposed `d_gold` row (matches the provisioned table)

```
query_id      -> d_queries.query_id
gold_node_id  -> nullable; exact node id when pinned
gold_label    -> "Theorem 7.7" | "Exercise 7.11" | "§1" | null
relevance     -> graded: 2 = primary answer, 1 = acceptable/related
rationale     -> free text
-- ASK: add (or stash in d_queries.notes) a pdf page range per gold:
--   gold_pdf_start:int, gold_pdf_end:int   (to score the label-less baseline)
```

If altering `d_gold` columns is undesirable, stash the page range in
`d_queries.notes` jsonb as `{"gold_pages": [[94,94]]}` — C will read either.

## Query categories C is built to exercise (spec §14)

- **direct** — "Theorem 7.7", "the definition of an open equivalence relation":
  C's exact-label boost + lexical should dominate.
- **conceptual** — "passages about quotient constructions", "smooth vs analytic":
  vector signal + section-node coarse-to-fine.
- **structural** — "what definitions occur in §7", "what proves Theorem 7.7":
  C uses `kind` + `proves` metadata (proof→theorem links exist in `meta.proves`).
- **graph_expansion** — depends on Track B's edges; C will degrade to
  section-membership if B isn't ready.

## Two concrete data facts D should bake into the gold

1. **Tu has no "Definition N.M" labels in the §1–§3 slice** — definitions are
   bold-inline ("Define the dual space V∨ …"). So a `direct` "definition of X"
   query has **no leaf node of kind=definition** to be gold; the right gold is
   the **section** or the bold sentence's enclosing exposition. C currently has
   0 `definition` leaves (a real book property, confirmed — see FINDINGS). Track
   A may recover bold-inline definitions; until then, gold for definition
   queries should target a `section` node or a page.
2. **"Problem N" vs "Exercise N" mismatch.** Tu's body labels exercises as
   `Exercise 7.11`, but cross-refs and the end-of-section block say `Problem
   7.11`. C's label-boost matches the *body* label. If a `direct` query says
   "Problem 7.11", please set `gold_label = "Exercise 7.11"` (the node's real
   label) OR list both — otherwise the exact-label signal is unfairly penalized.

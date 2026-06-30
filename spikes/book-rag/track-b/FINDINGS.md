# Track B — Document graph, references & validation — FINDINGS

Scope/contract: issue **#57** (Track B). Leads on **structure quality**.
Tables: `b_*` (consumes `a_*` or the seed fixture). Bucket: `track-b/`.

**Question:** from typed nodes, can we build the graph (`contains`/`parent_of`/
`next`/`previous`/`proven_by`/`has_equation`/`references`), enforce the §10
invariants, and resolve in-text cross-references ("by Theorem 4.7", "Problem
2.16") to node IDs?

> Fill in as you go.

## Feasibility
- Edge construction (which edge types are cheap/deterministic vs. hard): …
- Reference resolution approach: …

## Quality
- Invariant-violation report (counts by invariant): …
- Reference-resolution accuracy on sampled in-text refs: __ / __ correct …

## Speed / cost
- Graph build time for the slice: …

## Recommendation (1 paragraph)

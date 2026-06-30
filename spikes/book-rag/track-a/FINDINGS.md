# Track A — Structural extraction & the book skeleton — FINDINGS

Scope/contract: issue **#57** (Track A). Leads on **feasibility**. Owns
`_shared/schema.py`. Tables: `a_*`. Bucket: `track-a/`.

**Question:** can we deterministically turn Tu's PDF into the typed skeleton
(hierarchy + formal environments + page mapping + per-decision confidence),
leaning on the 269-entry outline — and where does determinism break?

> Fill in as you go. Numbers on the shared slice, not prose.

## Feasibility
- Hierarchy recovery (chapter/§section/subsection): …
- Environment recovery (def/thm/prop/lemma/cor/proof/example/remark/exercise): …
- Page mapping (pdf ↔ printed, the ~21 offset): …
- Where pure determinism breaks / where model help is needed: …

## Quality (fidelity scorecard)
| element | in slice | recovered | correctly located | notes |
|---|---|---|---|---|

## Speed / cost
- Extraction time for the slice / full book estimate: …

## The Tu-specific parser config (correcting the generic spec regex)
- section = `§N`, subsection = `N.M`, chapter = `Chapter K: Title`, exercises under `Problems`…

## Recommendation (1 paragraph)

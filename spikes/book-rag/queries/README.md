# queries/ — Track D's shared query set + gold

The measuring stick. File-mirror of the `d_queries` / `d_gold` tables so the
set is reviewable in git. Track C scores against these — C must not invent its
own. Categories: `direct` / `conceptual` / `structural` / `graph_expansion`,
all grounded in the shared slice (Tu Ch1 §1–§3 + Ch7 §7).

Suggested files: `queries.json` (query_id, category, query_text, intent) and
`gold.json` (query_id → [{gold_node_id|gold_label, relevance}]).

_Owned by Track D — published early to unblock Track C._

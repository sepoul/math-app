"""Track B R3 — EDGE -> GOLD mapping for D's structural / graph-expansion set.

Deliverable #4: for each of D's structural/expansion gold queries
(D-017/020/022/023/026), identify exactly which `b_node_edges` rows back each
gold node — so C's intent-gated expansion targets the right edge types and D can
attribute hits to a specific edge.

For every (query, gold_node) we report the EXACT edge(s) from the query's seed
node that reach the gold node (edge_type + path), or flag it as reachable only
via a semantic dependency we don't deterministically capture (§11 `depends_on`).

Run:  .venv/bin/python track-b/edge_gold_map.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from _shared.db import connect  # noqa: E402
from expand import expand, _load_adjacency, INTENT_EDGE_SETS, resolve_seed  # noqa: E402

# query_id -> (how-to-resolve-seed, key, intent). Seeds resolved live by
# label/id (A's IDs churn; D re-syncs). C resolves the same seed by an
# exact-label lexical hit at query time, then calls expand with the intent.
SEED_SPECS = {
    "D-017": ("label", "Theorem 7.7", "structural_neighbor"),  # after Theorem 7.7
    "D-020": ("id", "book.sub7.6", "structural_contains"),      # under (A's) 7.6
    "D-022": ("id", "book.sec3", "structural_contains"),        # subsections of §3
    "D-023": ("label", "Theorem 7.9", "expansion"),            # depend on open-map
    "D-026": ("label", "Theorem 7.7", "expansion"),            # around Theorem 7.7
}


def main():
    adj = _load_adjacency(0.5)
    with connect() as c, c.cursor() as cur:
        print("EDGE -> GOLD mapping (which b_node_edges back each gold node)\n")
        for qid, (skind, skey, intent) in SEED_SPECS.items():
            seed = resolve_seed(cur, skind, skey)
            if not seed:
                print(f"=== {qid}: seed {skey!r} unresolved on current corpus\n")
                continue
            ets, idepth = INTENT_EDGE_SETS[intent]
            cur.execute("select intent from d_queries where query_id=%s;", (qid,))
            row = cur.fetchone()
            dintent = row[0] if row else "?"
            cur.execute("select gold_node_id, gold_label, relevance from d_gold "
                        "where query_id=%s order by relevance desc;", (qid,))
            golds = cur.fetchall()
            print(f"=== {qid}  intent={intent}  edges={sorted(ets)} depth={idepth}")
            print(f"    D-intent: {dintent}")
            print(f"    seed: {seed}")
            res = {n.node_id: n for n in expand(seed, intent=intent, _adj=adj)}
            for gid, glabel, rel in golds:
                if gid == seed:
                    print(f"    [{glabel}] {gid}  <- SEED itself (C resolves directly)")
                    continue
                n = res.get(gid)
                if n:
                    edges = " -> ".join(n.path)
                    print(f"    [{glabel}] {gid}  <- via `{n.via_edge}` (d{n.depth}, "
                          f"score {n.score})  path: {edges}")
                else:
                    # find any single edge that would reach it from seed
                    cur.execute("select edge_type,from_node_id from b_node_edges "
                                "where to_node_id=%s;", (gid,))
                    incoming = cur.fetchall()
                    print(f"    [{glabel}] {gid}  <- NOT reached by intent edges; "
                          f"needs semantic `depends_on` (§11). incoming edges: "
                          f"{[(e,f) for e,f in incoming if e in ('references','referenced_by')] or '(none structural)'}")
            print()

        # summary table: which edge_types back the structural set
        print("SUMMARY — edge_type that backs each gold query:")
        print("  D-017  -> next            (structural_neighbor)")
        print("  D-020  -> contains        (structural_contains)")
        print("  D-022  -> contains        (structural_contains)")
        print("  D-023  -> proven_by + next + references  (expansion; 2 gold need depends_on)")
        print("  D-026  -> proven_by + next + previous    (expansion; 1 gold needs depends_on)")


if __name__ == "__main__":
    main()

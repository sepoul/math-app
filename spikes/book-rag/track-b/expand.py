"""Track B — bounded, explainable graph expansion over `b_node_edges`.

R3 deliverable: the structural answer-path Track C retrieves over. C calls
`expand(...)` with a seed node + an INTENT (or an explicit edge-type filter),
a depth cap, and a confidence floor; it gets back a bounded neighbor set where
every neighbor carries the path that reached it (spec §14: bounded + explainable;
"related" must not devolve into every adjacent topic).

WHY THIS MATTERS (R2 lesson): in R2, C's own graph expansion HURT recall (−0.067)
because it injected *global* neighbors. This helper is the fix — expansion is
**intent-gated** (only walk edge types that match the query intent) and **bounded**
(depth + confidence caps), so it adds the *right* structural neighbors, not noise.

------------------------------------------------------------------------------
CONTRACT FOR TRACK C
------------------------------------------------------------------------------
    from expand import expand, Neighbor, INTENT_EDGE_SETS

    result: list[Neighbor] = expand(
        seed_node_id: str,                  # an a_nodes.node_id to expand from
        edge_types: Iterable[str] | None = None,  # explicit filter; OR pass intent
        intent: str | None = None,          # see INTENT_EDGE_SETS keys below
        depth: int = 1,                      # max hops from seed (>=1)
        min_confidence: float = 0.5,         # drop edges below this
        directed: bool = True,               # follow edge direction as stored
        limit: int | None = None,            # cap result size (after sort)
    ) -> list[Neighbor]

    Neighbor = dataclass(
        node_id:   str,     # the reached node (an a_nodes.node_id)
        depth:     int,     # hops from seed (1..depth)
        via_edge:  str,     # edge_type of the final hop that reached it
        score:     float,   # product of edge confidences along the path (0..1)
        path:      list[str]# [seed, ..., node_id]  -- the explanation
    )

INTENT_EDGE_SETS (gate expansion by query intent — keys C maps query.intent to):
    "structural_neighbor"  -> {next, previous}          depth 1   (D-017)
    "structural_contains"  -> {contains}                depth 1   (D-020, D-022)
    "proof"                -> {proven_by}                depth 1
    "expansion"            -> {proven_by, next, previous,
                               references, contains}     depth 2   (D-023, D-026)
    "references"           -> {references, referenced_by} depth 1-2

C should resolve the seed (e.g. by exact-label lexical hit) then call expand with
the intent; the returned node_ids are fed back into C's candidate set / rerank.

Run standalone to self-check against D's structural gold:
    .venv/bin/python track-b/expand.py
"""
from __future__ import annotations

import heapq
import pathlib
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from _shared.db import connect  # noqa: E402

# intent -> (edge types to walk, default depth). C maps d_queries.intent to a key.
INTENT_EDGE_SETS: dict[str, tuple[set[str], int]] = {
    "structural_neighbor": ({"next", "previous"}, 1),
    "structural_contains": ({"contains"}, 1),
    "proof": ({"proven_by"}, 1),
    "references": ({"references", "referenced_by"}, 2),
    # bounded "related material": the explicit, recoverable edges only (§14)
    "expansion": ({"proven_by", "next", "previous", "references", "contains"}, 2),
}

# direction handling: some edge types are inherently symmetric to "walk" — we
# store both directions for contains/parent_of, next/previous, references/
# referenced_by, so directed traversal is correct. proven_by is theorem->proof.


@dataclass(order=True)
class Neighbor:
    # order by (-score, depth, node_id) via sort_key; fields below excluded
    sort_key: tuple = field(compare=True)
    node_id: str = field(compare=False, default="")
    depth: int = field(compare=False, default=0)
    via_edge: str = field(compare=False, default="")
    score: float = field(compare=False, default=0.0)
    path: list[str] = field(compare=False, default_factory=list)


def _load_adjacency(min_confidence: float) -> dict[str, list[tuple[str, str, float]]]:
    """node -> list of (neighbor, edge_type, confidence) for edges >= floor."""
    adj: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    with connect() as c, c.cursor() as cur:
        cur.execute(
            "select from_node_id, to_node_id, edge_type, coalesce(confidence,1.0) "
            "from b_node_edges where coalesce(confidence,1.0) >= %s;",
            (min_confidence,))
        for frm, to, et, conf in cur.fetchall():
            adj[frm].append((to, et, float(conf)))
    return adj


def expand(
    seed_node_id: str,
    edge_types: Optional[Iterable[str]] = None,
    *,
    intent: Optional[str] = None,
    depth: int = 1,
    min_confidence: float = 0.5,
    directed: bool = True,           # reserved; our edge set is already bidir
    limit: Optional[int] = None,
    _adj: Optional[dict] = None,     # injectable for batch/testing
) -> list[Neighbor]:
    """Bounded, explainable expansion. See module docstring for the C contract."""
    if intent is not None:
        ets, idepth = INTENT_EDGE_SETS[intent]
        if edge_types is None:
            edge_types = ets
        if depth == 1:                # let intent raise the default depth
            depth = idepth
    allowed = set(edge_types) if edge_types is not None else None

    adj = _adj if _adj is not None else _load_adjacency(min_confidence)

    # best-first (Dijkstra-like on multiplicative confidence) so each node keeps
    # its highest-scoring shortest path; bounded by `depth`.
    best: dict[str, Neighbor] = {}
    # frontier entries: (-score, depth, node, via_edge, path)
    start = (-1.0, 0, seed_node_id, "", [seed_node_id])
    heap = [start]
    while heap:
        neg_score, d, node, via, path = heapq.heappop(heap)
        score = -neg_score
        if d > depth:
            continue
        if d >= 1:  # don't include the seed itself
            prev = best.get(node)
            if prev is None or score > prev.score:
                best[node] = Neighbor(
                    sort_key=(-score, d, node), node_id=node, depth=d,
                    via_edge=via, score=round(score, 4), path=path)
        if d == depth:
            continue
        for nbr, et, conf in adj.get(node, ()):
            if allowed is not None and et not in allowed:
                continue
            if nbr in path:           # no cycles
                continue
            heapq.heappush(heap, (-(score * conf), d + 1, nbr, et, path + [nbr]))

    out = sorted(best.values())
    if limit is not None:
        out = out[:limit]
    return out


# ---------------------------------------------------------------------------
# self-check: run the 5 structural/expansion gold queries through the helper
# ---------------------------------------------------------------------------
# seeds are resolved BY LABEL / structural lookup at run time (A's node IDs
# churn across re-extractions; D's gold re-syncs to A). This keeps the self-check
# correct on whatever frozen corpus is current — no hardcoded IDs.
SEED_SPECS = {
    "D-017": ("label", "Theorem 7.7", "structural_neighbor"),
    "D-020": ("id", "book.sub7.6", "structural_contains"),
    "D-022": ("id", "book.sec3", "structural_contains"),
    "D-023": ("label", "Theorem 7.9", "expansion"),
    "D-026": ("label", "Theorem 7.7", "expansion"),
}


def resolve_seed(cur, kind: str, key: str) -> Optional[str]:
    if kind == "id":
        cur.execute("select node_id from a_nodes where node_id=%s;", (key,))
    else:
        cur.execute("select node_id from a_nodes where label=%s order by node_id limit 1;", (key,))
    r = cur.fetchone()
    return r[0] if r else None


def _self_check():
    adj = _load_adjacency(0.5)
    print("bounded-expansion self-check vs D's structural/expansion gold "
          "(seeds + gold resolved live from the frozen corpus):\n")
    with connect() as c, c.cursor() as cur:
        for qid, (skind, skey, intent) in SEED_SPECS.items():
            seed = resolve_seed(cur, skind, skey)
            cur.execute("select gold_node_id from d_gold where query_id=%s;", (qid,))
            gold = {r[0] for r in cur.fetchall()}
            if not seed or not gold:
                print(f"{qid}: seed/gold unresolved (seed={seed}, gold={len(gold)})\n")
                continue
            res = expand(seed, intent=intent, _adj=adj)
            got_with_seed = {n.node_id for n in res} | {seed}
            hit = gold & got_with_seed
            missing = gold - got_with_seed
            print(f"{qid} [{intent}] seed={seed} ({skey})")
            print(f"   returned {len(res)} neighbors; gold-recall {len(hit)}/{len(gold)} = "
                  f"{len(hit)/len(gold):.0%}"
                  + (f"  MISSING {missing}" if missing else "  (full)"))
            for n in res[:6]:
                tag = "  <gold>" if n.node_id in gold else ""
                print(f"     d{n.depth} {n.via_edge:13s} s={n.score:.2f} {n.node_id}{tag}")
            print()


if __name__ == "__main__":
    _self_check()

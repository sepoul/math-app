"""Document graph + reference resolution + bounded expansion — spike Track B.

Provenance: adapted from
  `origin/spike/graph-grounding:spikes/book-rag/track-b/graph_build.py`
  `origin/spike/graph-grounding:spikes/book-rag/track-b/expand.py`

The spike read nodes from the `a_nodes` table and wrote edges to `b_node_edges`;
this module operates purely in memory on the `ParsedNode`s produced by
`_extraction.parse_pdf`, and returns edge dicts the workflow maps into
`BookEdge`s. Two public entry points:

  * `build_graph(nodes)` — the deterministic + reference edge set
    (contains/parent_of/next/previous/proven_by/has_equation + resolved
    references/referenced_by). The `book_index` job (#63) mints these.
  * `expand(seed, edges, ...)` — the bounded, intent-gated neighbor walk the
    `book_retrieve` job (#64) uses over the persisted edges. Kept here (not in
    the index path) so #64 imports one graph module; identical algorithm to the
    spike's `expand.py`, refactored to take an explicit edge list instead of a
    DB adjacency load (no tenant-DB round-trip inside the retrieve hot loop).

The reference resolver drops the spike's Tu-specific `SLICE_PREFIXES` gate (that
was a slice-eval device): a reference resolves iff a matching node exists,
otherwise it is simply not promoted to an edge. Pure string + dict work, no I/O.
"""
from __future__ import annotations

import heapq
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from mathai.math_book._extraction import ParsedNode

THM_LIKE = {"theorem", "proposition", "lemma", "corollary"}
_LABEL_NUM = re.compile(r"(\d+(?:\.\d+)*)")


# ============================================================================
# 1. deterministic edges  (track-b/graph_build.py:build_edges)
# ============================================================================
def _order_key(n: ParsedNode) -> tuple:
    page = n.page_pdf_start if n.page_pdf_start is not None else 10 ** 6
    m = _LABEL_NUM.search(n.label or "")
    nums = tuple(int(x) for x in m.group(1).split(".")) if m else (10 ** 6,)
    return (page,) + nums


def _build_structural_edges(nodes: list[ParsedNode]) -> list[dict]:
    by_id = {n.node_id: n for n in nodes}
    edges: list[dict] = []

    def add(frm, to, et, conf, ev):
        edges.append({"from_node_id": frm, "to_node_id": to, "edge_type": et,
                      "confidence": conf, "evidence": ev})

    children: dict[str, list[ParsedNode]] = {}
    for n in nodes:
        if n.parent_id and n.parent_id in by_id:
            add(n.parent_id, n.node_id, "contains", 1.0, ["parent_id from hierarchy"])
            add(n.node_id, n.parent_id, "parent_of", 1.0, ["inverse of contains"])
            children.setdefault(n.parent_id, []).append(n)

    for _pid, sibs in children.items():
        sibs_sorted = sorted(sibs, key=_order_key)
        for a, b in zip(sibs_sorted, sibs_sorted[1:]):
            add(a.node_id, b.node_id, "next", 0.95, ["reading-order sibling chain"])
            add(b.node_id, a.node_id, "previous", 0.95, ["reading-order sibling chain"])

    for n in nodes:
        if n.kind == "proof" and n.proves and n.proves in by_id:
            tgt = by_id[n.proves]
            conf = 0.97 if tgt.kind in THM_LIKE else 0.6
            add(n.proves, n.node_id, "proven_by", conf,
                [f"proof attaches to {tgt.kind} {tgt.label or ''}".strip()])

    for n in nodes:
        for eq in n.math_region_ids:
            add(n.node_id, eq, "has_equation", 0.9, ["equation in math_region_ids"])

    return edges


# ============================================================================
# 2. reference resolution  (track-b/graph_build.py:resolve_references)
# ============================================================================
ENV_KINDS = "Theorem|Proposition|Lemma|Corollary|Definition|Example|Remark|Exercise"
REF_PATTERNS = [
    ("env", re.compile(rf"\b({ENV_KINDS})\s+([A-Z]?\.?\d+(?:\.\d+)*)")),
    ("problem", re.compile(r"\bProblem\s+(\d+(?:\.\d+)*)")),
    ("section", re.compile(r"§\s*(\d+)")),
    ("chapter", re.compile(r"\bChapter\s+(\d+)")),
]


@dataclass
class _Ref:
    src_node_id: str
    raw_mention: str
    resolved_node_id: Optional[str]
    confidence: float


def _build_label_index(nodes: list[ParsedNode]):
    env_idx: dict[str, str] = {}
    exer_idx: dict[str, str] = {}
    sec_idx: dict[str, str] = {}
    chap_idx: dict[str, str] = {}
    for n in nodes:
        if not n.label:
            continue
        lab = n.label.strip()
        if n.kind == "exercise":
            m = _LABEL_NUM.search(lab)
            if m:
                exer_idx[m.group(1)] = n.node_id
        elif n.kind in (THM_LIKE | {"definition", "example", "remark"}):
            env_idx[lab.lower()] = n.node_id
        elif n.kind == "section":
            m = re.search(r"(\d+)", lab)
            if m:
                sec_idx[m.group(1)] = n.node_id
        elif n.kind == "chapter":
            m = re.search(r"(\d+)", lab)
            if m:
                chap_idx[m.group(1)] = n.node_id
    return env_idx, exer_idx, sec_idx, chap_idx


def _resolve_references(nodes: list[ParsedNode]) -> list[_Ref]:
    """Resolve in-text citations to node_ids. Unlike the spike, a mention that
    finds no matching node is simply left unresolved (no in-slice gate) — the
    reference-edge step only promotes resolved ones."""
    env_idx, exer_idx, sec_idx, chap_idx = _build_label_index(nodes)
    refs: list[_Ref] = []
    seen: set[tuple] = set()
    for n in nodes:
        text = n.text_normalized or n.text_raw or ""
        for kind, pat in REF_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group(0).strip()
                key = (n.node_id, raw)
                if key in seen:
                    continue
                seen.add(key)
                resolved_id = None
                conf = 0.0
                if kind == "env":
                    env_kind, num = m.group(1), m.group(2)
                    if env_kind == "Exercise":
                        resolved_id = exer_idx.get(num)
                    else:
                        resolved_id = env_idx.get(f"{env_kind} {num}".lower())
                    conf = 0.95 if resolved_id else 0.0
                elif kind == "problem":
                    resolved_id = exer_idx.get(m.group(1))
                    conf = 0.95 if resolved_id else 0.0
                elif kind == "section":
                    resolved_id = sec_idx.get(m.group(1))
                    conf = 0.9 if resolved_id else 0.0
                elif kind == "chapter":
                    resolved_id = chap_idx.get(m.group(1))
                    conf = 0.9 if resolved_id else 0.0
                refs.append(_Ref(n.node_id, raw, resolved_id, conf))
    return refs


def _reference_edges(refs: list[_Ref]) -> list[dict]:
    """Promote RESOLVED references to references/referenced_by edge pairs.
    (track-b/graph_build.py:reference_edges)"""
    edges: list[dict] = []
    seen: set[tuple] = set()
    for r in refs:
        if not r.resolved_node_id:
            continue
        src, dst = r.src_node_id, r.resolved_node_id
        if src == dst:
            continue
        for frm, to, et in ((src, dst, "references"), (dst, src, "referenced_by")):
            k = (frm, to, et)
            if k in seen:
                continue
            seen.add(k)
            edges.append({"from_node_id": frm, "to_node_id": to, "edge_type": et,
                          "confidence": r.confidence,
                          "evidence": [f"in-text mention {r.raw_mention!r}"]})
    return edges


def build_graph(nodes: list[ParsedNode]) -> list[dict]:
    """Full edge set for the skeleton: deterministic structure + resolved
    references. Each edge is `{from_node_id, to_node_id, edge_type, confidence,
    evidence}` — the workflow maps these into `BookEdge`s."""
    refs = _resolve_references(nodes)
    return _build_structural_edges(nodes) + _reference_edges(refs)


# ============================================================================
# 3. bounded, intent-gated expansion  (track-b/expand.py:expand)  — for #64
# ============================================================================
INTENT_EDGE_SETS: dict[str, tuple[set[str], int]] = {
    "structural_neighbor": ({"next", "previous"}, 1),
    "structural_contains": ({"contains"}, 1),
    "proof": ({"proven_by"}, 1),
    "references": ({"references", "referenced_by"}, 2),
    "expansion": ({"proven_by", "next", "previous", "references", "contains",
                   "depends_on", "depended_on_by"}, 2),
    "expansion_deterministic": ({"proven_by", "next", "previous", "references",
                                 "contains"}, 2),
    "dependencies": ({"depends_on", "depended_on_by"}, 2),
}


@dataclass(order=True)
class Neighbor:
    sort_key: tuple = field(compare=True)
    node_id: str = field(compare=False, default="")
    depth: int = field(compare=False, default=0)
    via_edge: str = field(compare=False, default="")
    score: float = field(compare=False, default=0.0)
    path: list[str] = field(compare=False, default_factory=list)


def _adjacency(edges: list[dict], min_confidence: float) -> dict[str, list[tuple[str, str, float]]]:
    adj: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for e in edges:
        conf = float(e.get("confidence") if e.get("confidence") is not None else 1.0)
        if conf >= min_confidence:
            adj[e["from_node_id"]].append((e["to_node_id"], e["edge_type"], conf))
    return adj


def expand(
    seed_node_id: str,
    edges: list[dict],
    edge_types: Optional[Iterable[str]] = None,
    *,
    intent: Optional[str] = None,
    depth: int = 1,
    min_confidence: float = 0.5,
    limit: Optional[int] = None,
) -> list[Neighbor]:
    """Bounded, explainable expansion over `edges` (Dijkstra on multiplicative
    edge confidence). Intent-gated: only walk edge types matching the query
    intent. Identical algorithm to `spike/graph-grounding:track-b/expand.py`,
    refactored to take an explicit edge list rather than loading a DB adjacency."""
    if intent is not None:
        ets, idepth = INTENT_EDGE_SETS[intent]
        if edge_types is None:
            edge_types = ets
        if depth == 1:
            depth = idepth
    allowed = set(edge_types) if edge_types is not None else None
    adj = _adjacency(edges, min_confidence)

    best: dict[str, Neighbor] = {}
    heap = [(-1.0, 0, seed_node_id, "", [seed_node_id])]
    while heap:
        neg_score, d, node, via, path = heapq.heappop(heap)
        score = -neg_score
        if d > depth:
            continue
        if d >= 1:
            prev = best.get(node)
            if prev is None or score > prev.score:
                best[node] = Neighbor(sort_key=(-score, d, node), node_id=node,
                                      depth=d, via_edge=via, score=round(score, 4),
                                      path=path)
        if d == depth:
            continue
        for nbr, et, conf in adj.get(node, ()):
            if allowed is not None and et not in allowed:
                continue
            if nbr in path:
                continue
            heapq.heappush(heap, (-(score * conf), d + 1, nbr, et, path + [nbr]))

    out = sorted(best.values())
    return out[:limit] if limit is not None else out

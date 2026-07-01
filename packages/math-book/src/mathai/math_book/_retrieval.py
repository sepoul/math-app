"""Hybrid retrieval + intent-gated graph expansion + Claude rerank — spike Track C.

Provenance: adapted from the LOCKED `C_full` retriever
  `origin/spike/hybrid-retrieval:spikes/book-rag/track-c/retrieve_r2.py`
  (`intent_boosts`, `label_targets`, `is_structural_intent`, `Retriever.hybrid`,
   the graph-expansion + section-demote logic, `C_FULL_CFG`)
  + the reranker `…/track-c/rerank.py` (`claude-haiku-4-5`, JSON index ordering).

`C_full` behavior the spike locked (right-place recall ~0.85, MRR ~0.91,
traceability ~1.0): min-max-fused lexical(FTS) + vector(cosine) + type boost
(intent→kind) + exact-label boost, section-node demotion for leaf-answer queries,
INTENT-GATED graph expansion (structural queries only — global expansion hurt
recall), then a Claude rerank over the top pool.

Adaptations for the platform:
  * the two legs run over the domain `math_book_chunks` table via `VectorStore`
    (`knn_query` / `lexical_query`), not the spike's `c_chunks`;
  * graph expansion walks the `BookStructureArtifact` edges via
    `_graph.expand(...)` (the same intent-gated bounded walk) instead of a
    `b_node_edges` table read;
  * the reranker is the platform `basic_agent(model="claude-haiku-4-5")`
    (pydantic_ai) rather than a raw `anthropic` client — text-in/rank-out, never
    invents passages, degrades to identity order on any failure;
  * `heading_path` / `page` for source-traceability come from the structure
    artifact's `BookNode`s (joined on node_id), keeping the chunk table lean.

`basic_agent` / anthropic are imported lazily inside `rerank` so this module
imports without the AI stack present.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from mathai.math_book._graph import expand

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ai_platform.ai.providers.embeddings import EmbeddingsInterpreter

    from mathai.math_book.vector_store import VectorStore

RERANK_MODEL = "claude-haiku-4-5"  # spike's rerank model (cheap/fast bulk scorer)

# fusion weights — the spike's C_FULL_CFG defaults (retrieve_r2.py:hybrid).
W_VEC = 1.0
W_LEX = 1.0
W_TYPE = 0.6
W_LABEL = 2.0
SECTION_DEMOTE = -0.6  # leaf-answer queries: push section/subsection nodes down
POOL = 50              # candidate pool per leg (C_FULL_CFG POOL)
RERANK_POOL = 12       # top-N handed to the reranker (C_FULL_CFG rerank_pool)


# ---- intent → type boost (retrieve_r2.py:intent_boosts) --------------------
def intent_boosts(query: str) -> dict[str, float]:
    q = query.lower()
    b: dict[str, float] = {}

    def add(kinds, w):
        for k in kinds:
            b[k] = max(b.get(k, 0.0), w)

    if re.search(r"\b(what is|define|definition|meaning of)\b", q):
        add(["definition"], 1.0)
        add(["subsection", "remark"], 0.3)
    if re.search(r"\b(theorem|prove|proof|proposition|lemma|corollary|show that|criterion|condition)\b", q):
        add(["theorem", "proposition", "lemma", "corollary"], 0.8)
        add(["proof"], 0.5)
    if re.search(r"\b(why|because|how do we know|need(ed)? to prove)\b", q):
        add(["proof", "lemma", "theorem"], 0.6)
    if re.search(r"\b(example|intuition|illustrat|gluing|e\.g\.|for instance)\b", q):
        add(["example", "remark"], 0.9)
    if re.search(r"\b(problem|exercise)\b", q):
        add(["exercise"], 1.0)
    if re.search(r"\b(subsection|which .*(are|occur) in|list the|in §|in section)\b", q):
        add(["subsection"], 0.5)
    return b


LABEL_IN_QUERY = re.compile(
    r"\b(theorem|proposition|lemma|corollary|definition|example|remark|exercise|problem)\s+(\d+(?:\.\w+)?)",
    re.I)


def label_targets(query: str) -> list[str]:
    out = []
    for m in LABEL_IN_QUERY.finditer(query):
        kind = m.group(1).capitalize()
        if kind == "Problem":
            kind = "Exercise"  # Tu body-label convention
        out.append(f"{kind} {m.group(2)}".lower())
    return out


# ---- query intent: gate graph expansion (retrieve_r2.py:is_structural_intent)
STRUCTURAL_RE = re.compile(
    r"\b(what comes (immediately )?(before|after)|right (before|after)|which (definitions|"
    r"results|propositions|corollaries|theorems|lemmas|subsections)|list the subsections|"
    r"occur in|are in subsection|in §|proof attached|attached to|depend on|build on|"
    r"everything needed|material around|results that)\b", re.I)


def is_structural_intent(query: str) -> bool:
    """True for structural / graph-expansion queries — the ones that benefit
    from walking the skeleton edges. Direct/conceptual queries do NOT get graph
    expansion (the spike's −0.067 regression: global neighbour injection displaced
    relevant direct hits within k)."""
    return bool(STRUCTURAL_RE.search(query))


SECTION_QUERY_RE = re.compile(r"\b(subsection|section|§|atlas|chapter)\b", re.I)

# edge-type weights for expanded neighbours (retrieve_r2.py graph block).
_EDGE_W = {"next": 0.95, "previous": 0.95, "proven_by": 0.9,
           "contains": 0.85, "references": 0.7, "referenced_by": 0.7}


@dataclass
class Cand:
    """A scored candidate — carries everything the result hit needs for source
    traceability (node_id + label + page + heading_path) + explainable signals."""

    chunk_id: str
    node_id: Optional[str]
    kind: Optional[str]
    label: Optional[str]
    heading_path: Optional[list]
    page: Optional[int]
    text: str
    score: float
    signals: dict = field(default_factory=dict)


def _minmax(d: dict[str, float]) -> dict[str, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


class BookRetriever:
    """The domain `C_full` retriever: hybrid + intent-gated expansion + rerank.

    `vector_store` runs the two legs over `math_book_chunks`; `embeddings`
    embeds the query; `edges` are the `BookStructureArtifact` edges (dicts:
    `{from_node_id,to_node_id,edge_type,confidence}`) for graph expansion;
    `node_index` maps node_id → `BookNode` for source-traceability enrichment.
    `rerank_agent` is an optional pre-built pydantic_ai agent (Claude); when
    None and `rerank=True`, one is built lazily.
    """

    def __init__(
        self,
        *,
        book_id: str,
        vector_store: "VectorStore",
        embeddings: "EmbeddingsInterpreter",
        edges: Optional[list[dict]] = None,
        node_index: Optional[dict] = None,  # node_id -> BookNode
    ) -> None:
        self.book_id = book_id
        self.vs = vector_store
        self.embeddings = embeddings
        self.edges = edges or []
        self.node_index = node_index or {}

    # -- source-traceability enrichment from the structure artifact ---------
    def _enrich(self, c: Cand) -> Cand:
        """Fill label/page/heading_path from the structure artifact's node when
        the chunk row didn't carry them (chunk rows keep only node_id/kind/source
        to stay lean; the node is the citation source of truth)."""
        node = self.node_index.get(c.node_id) if c.node_id else None
        if node is not None:
            c.label = c.label or getattr(node, "label", None)
            c.page = c.page if c.page is not None else getattr(node, "page", None)
            if not c.heading_path:
                c.heading_path = list(getattr(node, "heading_path", []) or [])
        return c

    # -- the hybrid (retrieve_r2.py:Retriever.hybrid, C_full config) --------
    def hybrid(self, query: str, k: int = 8, *, rerank: bool = True) -> list[Cand]:
        qvec = self.embeddings.embed(query).vector

        vec_hits = self.vs.knn_query(self.book_id, qvec, POOL)
        lex_hits = self.vs.lexical_query(self.book_id, query, POOL)

        vec_n = _minmax({h.chunk_id: h.score for h in vec_hits})
        lex_n = _minmax({h.chunk_id: h.score for h in lex_hits})

        by_id: dict[str, "object"] = {}
        for h in lex_hits + vec_hits:
            by_id.setdefault(h.chunk_id, h)

        boosts = intent_boosts(query)
        tgts = label_targets(query)
        section_query = bool(SECTION_QUERY_RE.search(query))

        scored: list[Cand] = []
        for cid, h in by_id.items():
            lv = lex_n.get(cid, 0.0)
            vv = vec_n.get(cid, 0.0)
            tb = boosts.get(h.kind, 0.0) if h.kind else 0.0
            lb = 1.0 if (h.node_id and self._label_of(h) in tgts) else 0.0
            sd = (SECTION_DEMOTE if (not section_query
                                     and h.kind in ("section", "subsection")) else 0.0)
            final = W_VEC * vv + W_LEX * lv + W_TYPE * tb + W_LABEL * lb + sd
            sig = {"vector_n": round(vv, 3), "lexical_n": round(lv, 3),
                   "type_boost": tb, "label_boost": lb}
            if sd:
                sig["section_demote"] = sd
            scored.append(self._enrich(Cand(
                chunk_id=h.chunk_id, node_id=h.node_id, kind=h.kind,
                label=None, heading_path=None, page=None,
                text=h.text, score=final, signals=sig)))
        scored.sort(key=lambda x: x.score, reverse=True)

        # intent-gated graph expansion (structural queries only)
        if is_structural_intent(query) and self.edges:
            scored = self._expand(query, scored)

        if rerank:
            scored = self._rerank(query, scored[:RERANK_POOL]) + scored[RERANK_POOL:]
        return scored[:k]

    def _label_of(self, hit) -> str:
        """Lowercased label of a chunk hit (from its node, for label-boost match)."""
        node = self.node_index.get(hit.node_id) if hit.node_id else None
        lab = getattr(node, "label", None) if node else None
        return (lab or "").lower()

    # -- intent-gated graph expansion (retrieve_r2.py graph block) ----------
    def _expand(self, query: str, scored: list[Cand]) -> list[Cand]:
        """Expand from the TOP-2 seeds via `_graph.expand` (intent='expansion'),
        injecting/promoting the reached neighbours just below the top seed —
        weighted by edge type. The expanded neighbour is often the structural
        answer ("what comes after Theorem 7.7" → the next-edge corollary)."""
        top_seeds = [c for c in scored[:2] if c.node_id]
        if not top_seeds:
            return scored
        top = scored[0].score if scored else 1.0

        # reached node_ids (+ the edge that reached each) via the bounded walk.
        reached: dict[str, str] = {}
        for seed in top_seeds:
            for nb in expand(seed.node_id, self.edges, intent="expansion"):
                reached.setdefault(nb.node_id, nb.via_edge)
        if not reached:
            return scored

        # fetch chunk rows for the reached nodes.
        nbr_hits = self.vs.get_chunks_by_node(self.book_id, list(reached))
        by_cid = {c.chunk_id: c for c in scored}
        for h in nbr_hits:
            et = reached.get(h.node_id, "")
            gscore = top * _EDGE_W.get(et, 0.6)  # just below the top seed
            existing = by_cid.get(h.chunk_id)
            if existing is None:  # inject absent neighbour
                c = self._enrich(Cand(
                    chunk_id=h.chunk_id, node_id=h.node_id, kind=h.kind,
                    label=None, heading_path=None, page=None,
                    text=h.text, score=gscore,
                    signals={"graph": et, "graph_injected": True}))
                scored.append(c)
                by_cid[h.chunk_id] = c
            elif gscore > existing.score:  # promote present neighbour
                existing.score = gscore
                existing.signals = {**existing.signals, "graph_promoted": et}
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    # -- Claude rerank via basic_agent (rerank.py, platform provider) -------
    def _rerank(self, query: str, cands: list[Cand]) -> list[Cand]:
        """Rank the candidates with a tightly-constrained Claude scorer (bulk
        relevance, one call, JSON index array). Degrades to identity order on any
        failure — a rerank must never drop candidates. Uses the platform
        `basic_agent` (pydantic_ai + Anthropic)."""
        if not cands:
            return cands
        order = _claude_rerank(query, cands)
        n = len(order)
        ranked: list[Cand] = []
        for pos, idx in enumerate(order):
            if 0 <= idx < len(cands):
                c = cands[idx]
                c.score = 100.0 + (n - pos)  # dominate the fused score, keep order
                c.signals = {**c.signals, "rerank_pos": pos}
                ranked.append(c)
        ranked_ids = {c.chunk_id for c in ranked}
        ranked += [c for c in cands if c.chunk_id not in ranked_ids]
        return ranked


_RERANK_SYSTEM = (
    "You are a retrieval reranker for a mathematics textbook. Given a query and a "
    "numbered list of candidate passages, rank them by how well each ANSWERS the "
    "query. Consider each passage's type (definition/theorem/proof/example/"
    "exercise/section), its label, and its text. You only RANK the given "
    "candidates; never invent passages or text. Respond with ONLY a JSON array of "
    "candidate numbers, best first, e.g. [3,1,2]. Include every candidate number "
    "exactly once."
)


def _claude_rerank(query: str, cands: list[Cand]) -> list[int]:
    """One Claude call → a permutation of indices into `cands` (best first).
    Identity order on any error/parse failure. Ported from
    `spike/hybrid-retrieval:track-c/rerank.py`, using the platform `basic_agent`."""
    lines = []
    for i, c in enumerate(cands):
        kind = c.kind or "?"
        label = c.label or ""
        text = " ".join((c.text or "").split())[:180]
        lines.append(f"[{i}] ({kind} {label}) {text}")
    user = (f"Query: {query}\n\nCandidates:\n" + "\n".join(lines)
            + "\n\nReturn the JSON array of candidate numbers, best first.")
    try:
        from ai_platform.ai.providers.basic_agent import basic_agent

        agent = basic_agent(model=RERANK_MODEL, instructions=_RERANK_SYSTEM)
        result = agent.run_sync(user)
        text = getattr(result, "output", None) or getattr(result, "data", "") or ""
        return _parse_order(str(text), len(cands))
    except Exception:
        return list(range(len(cands)))


def _parse_order(text: str, n: int) -> list[int]:
    import json

    m = re.search(r"\[[\d,\s]*\]", text)
    if not m:
        return list(range(n))
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return list(range(n))
    seen, order = set(), []
    for x in arr:
        if isinstance(x, int) and 0 <= x < n and x not in seen:
            order.append(x)
            seen.add(x)
    for i in range(n):  # append any dropped, preserving completeness
        if i not in seen:
            order.append(i)
    return order

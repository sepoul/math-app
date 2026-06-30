"""Track C — R2 retriever: structure-aware hybrid + graph expansion + rerank.

Built for the harness contract `retrieve_fn(query_text, k) -> list[dict]` where
each dict carries node_id / chunk_id / score / label / page_pdf_start /
heading_path / signals (so the §17 traceability + label matching score).

Performance fixes over R1:
  - ONE shared psycopg connection for the whole eval run (R1 paid ~800ms TLS
    per primitive). `Retriever` holds the connection; `close()` when done.
  - A process-local embedding cache keyed on query text (the query embedding is
    the ~600ms cost; identical queries / ablation reruns hit the cache).

Signals (spec §13 fused score):
  final = w_vec·vec_n + w_lex·lex_n + w_type·type_boost + w_label·label_boost
        (+ rerank replaces the score when rerank=True)
Graph expansion (spec §14, bounded): from the top structured seeds, walk Track
B's edges (proven_by / next / previous / contains) one hop and inject neighbors,
scored just below their seed. `references` edges are walked too if/when B lands
them (currently 0).

Ablation knobs: use_lexical / use_vector / use_type / use_label / use_graph /
rerank — the harness drives each as a separate run_label.
"""
from __future__ import annotations

import re
import sys
import time
import pathlib
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _shared.db import connect, SCHEMA, load_env  # noqa: E402

EMBED_MODEL = "text-embedding-3-small"


# ---- intent → type boost (spec §13) ---------------------------------------
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
        out.append(f"{kind} {m.group(2)}")
    return out


@dataclass
class Cand:
    chunk_id: str
    node_id: str | None
    kind: str | None
    label: str | None
    heading_path: list | None
    page: int | None
    text: str
    score: float
    signals: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "chunk_id": self.chunk_id,
                "score": round(float(self.score), 4), "label": self.label,
                "page_pdf_start": self.page, "heading_path": self.heading_path,
                "signals": {**self.signals, "kind": self.kind}}


def _minmax(d: dict[str, float]) -> dict[str, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


# ---- query intent (R3): gate graph expansion to where it helps -------------
STRUCTURAL_RE = re.compile(
    r"\b(what comes (immediately )?(before|after)|right (before|after)|which (definitions|"
    r"results|propositions|corollaries|theorems|lemmas|subsections)|list the subsections|"
    r"occur in|are in subsection|in §|proof attached|attached to|depend on|build on|"
    r"everything needed|material around|results that)\b", re.I)


def is_structural_intent(query: str) -> bool:
    """True for structural / graph-expansion queries (the ones that benefit from
    walking B's edges). Direct/conceptual queries do NOT get graph expansion —
    that was the R2 −0.067 regression: globally injecting neighbours displaced
    relevant direct hits within k."""
    return bool(STRUCTURAL_RE.search(query))


class Retriever:
    """Holds ONE connection + an embedding cache for a whole eval run.

    The connection is autocommit with a server-side statement_timeout so a single
    stalled query can't wedge the whole 234-query eval (the R1/R2 hang we hit was
    one long-lived connection blocking with no timeout). `_run` reconnects + retries
    once on a dropped/timed-out connection.
    """

    def __init__(self):
        self.conn = self._fresh()
        self._emb_cache: dict[str, np.ndarray] = {}
        self._oa = None
        self.embed_calls = 0
        self.embed_seconds = 0.0

    @staticmethod
    def _fresh():
        conn = connect(autocommit=True)
        with conn.cursor() as cur:
            cur.execute("set statement_timeout = 15000;")  # 15s hard cap per query
        return conn

    def _run(self, sql: str, params: tuple):
        """Execute + fetchall, reconnecting once on a stale/timed-out connection."""
        import psycopg
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.fetchall()
            except (psycopg.OperationalError, psycopg.InterfaceError):
                if attempt == 2:
                    raise
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = self._fresh()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # -- embedding (cached) --
    def embed(self, text: str) -> np.ndarray:
        if text in self._emb_cache:
            return self._emb_cache[text]
        if self._oa is None:
            from openai import OpenAI
            self._oa = OpenAI(api_key=load_env()["OPENAI_API_KEY"])
        t0 = time.perf_counter()
        v = np.asarray(self._oa.embeddings.create(model=EMBED_MODEL, input=[text])
                       .data[0].embedding, dtype=np.float32)
        self.embed_seconds += time.perf_counter() - t0
        self.embed_calls += 1
        self._emb_cache[text] = v
        return v

    # -- primitives over c_chunks --
    def lexical(self, query: str, k: int) -> list[Cand]:
        rows = self._run(
            f"""select chunk_id, node_id, kind, label, heading_path,
                      page_pdf_start, text,
                      ts_rank(tsv, plainto_tsquery('english', %s)) r
                from {SCHEMA}.c_chunks
                where tsv @@ plainto_tsquery('english', %s)
                order by r desc limit %s""", (query, query, k))
        return [Cand(r[0], r[1], r[2], r[3], r[4], r[5], r[6], float(r[7]),
                     {"lexical": float(r[7])}) for r in rows]

    def vector(self, query: str, k: int, qv=None) -> list[Cand]:
        qv = qv if qv is not None else self.embed(query)
        rows = self._run(
            f"""select chunk_id, node_id, kind, label, heading_path,
                      page_pdf_start, text, 1-(embedding <=> %s) sim
                from {SCHEMA}.c_chunks where embedding is not null
                order by embedding <=> %s limit %s""", (qv, qv, k))
        return [Cand(r[0], r[1], r[2], r[3], r[4], r[5], r[6], float(r[7]),
                     {"vector": float(r[7])}) for r in rows]

    # -- baseline primitives over c_baseline_chunks --
    def baseline_vector(self, query: str, k: int) -> list[Cand]:
        qv = self.embed(query)
        rows = self._run(
            f"""select chunk_id, page_pdf_start, text, 1-(embedding <=> %s) sim
                from {SCHEMA}.c_baseline_chunks where embedding is not null
                order by embedding <=> %s limit %s""", (qv, qv, k))
        return [Cand(r[0], None, None, None, None, r[1], r[2], float(r[3]),
                     {"vector": float(r[3])}) for r in rows]

    def baseline_lexical(self, query: str, k: int) -> list[Cand]:
        rows = self._run(
            f"""select chunk_id, page_pdf_start, text,
                      ts_rank(tsv, plainto_tsquery('english', %s)) r
                from {SCHEMA}.c_baseline_chunks
                where tsv @@ plainto_tsquery('english', %s)
                order by r desc limit %s""", (query, query, k))
        return [Cand(r[0], None, None, None, None, r[1], r[2], float(r[3]),
                     {"lexical": float(r[3])}) for r in rows]

    # -- graph expansion (spec §14): one bounded hop over B's edges --
    def expand(self, seeds: list[Cand], hops: int = 1,
               edge_types=("proven_by", "next", "previous", "contains", "references")) -> list[Cand]:
        if not seeds:
            return []
        seed_ids = [s.node_id for s in seeds if s.node_id]
        if not seed_ids:
            return []
        found: dict[str, Cand] = {}
        frontier = seed_ids
        seen = set(seed_ids)
        for _ in range(hops):
            edge_rows = self._run(
                f"""select from_node_id, to_node_id, edge_type
                    from {SCHEMA}.b_node_edges
                    where from_node_id = any(%s) and edge_type = any(%s)""",
                (frontier, list(edge_types)))
            nbrs = [(t, et) for (f, t, et) in edge_rows if t not in seen]
            if not nbrs:
                break
            nbr_ids = list({t for t, _ in nbrs})
            crows = self._run(
                f"""select chunk_id, node_id, kind, label, heading_path,
                          page_pdf_start, text
                    from {SCHEMA}.c_chunks where node_id = any(%s)""", (nbr_ids,))
            rows = {r[1]: r for r in crows}
            for t, et in nbrs:
                if t in rows and t not in found:
                    r = rows[t]
                    found[t] = Cand(r[0], r[1], r[2], r[3], r[4], r[5], r[6],
                                    0.0, {"graph": et})
            seen.update(nbr_ids)
            frontier = nbr_ids
        return list(found.values())

    # -- the hybrid --
    def hybrid(self, query: str, k: int = 10, pool: int = 30,
               w_vec=1.0, w_lex=1.0, w_type=0.6, w_label=2.0, w_graph=0.4,
               use_lexical=True, use_vector=True, use_type=True,
               use_label=True, use_graph=False, gate_graph=True,
               coarse_to_fine=False, rerank=False, rerank_pool=12) -> list[Cand]:
        qv = self.embed(query) if use_vector else None
        lex = self.lexical(query, pool) if use_lexical else []
        vec = self.vector(query, pool, qv=qv) if use_vector else []
        lex_n = _minmax({h.chunk_id: h.score for h in lex})
        vec_n = _minmax({h.chunk_id: h.score for h in vec})

        by_id: dict[str, Cand] = {}
        for h in lex + vec:
            by_id.setdefault(h.chunk_id, h)

        boosts = intent_boosts(query) if use_type else {}
        tgts = [t.lower() for t in label_targets(query)] if use_label else []
        # coarse-to-fine (§12): boost leaves whose section was top-ranked among sections
        cf_sections = self._coarse_sections(query, qv, k=3) if coarse_to_fine else set()

        scored: list[Cand] = []
        for cid, h in by_id.items():
            lv = lex_n.get(cid, 0.0)
            vv = vec_n.get(cid, 0.0)
            tb = boosts.get(h.kind, 0.0) if (use_type and h.kind) else 0.0
            lb = 1.0 if (use_label and h.label and h.label.lower() in tgts) else 0.0
            cf = 0.3 if (coarse_to_fine and self._parent_section(h) in cf_sections) else 0.0
            final = w_vec * vv + w_lex * lv + w_type * tb + w_label * lb + cf
            sig = {"vector_n": round(vv, 3), "lexical_n": round(lv, 3),
                   "type_boost": tb, "label_boost": lb}
            if cf:
                sig["coarse_to_fine"] = cf
            scored.append(Cand(h.chunk_id, h.node_id, h.kind, h.label, h.heading_path,
                               h.page, h.text, final, sig))
        scored.sort(key=lambda x: x.score, reverse=True)

        # intent-gated graph expansion: only for structural/graph-expansion queries
        do_expand = use_graph and (not gate_graph or is_structural_intent(query))
        if do_expand:
            top_seeds = scored[:5]
            base = scored[0].score if scored else 1.0
            present = {c.chunk_id for c in scored}
            for nb in self.expand(top_seeds):
                if nb.chunk_id not in present:
                    nb.score = base * 0.5 + w_graph  # strictly below seeds
                    nb.signals = {**nb.signals, "graph_injected": True}
                    scored.append(nb)
            scored.sort(key=lambda x: x.score, reverse=True)

        if rerank:
            scored = self.rerank(query, scored[:rerank_pool]) + scored[rerank_pool:]
        return scored[:k]

    # -- coarse-to-fine helpers (§12) --
    @staticmethod
    def _parent_section(h: "Cand") -> str | None:
        """node_id of the enclosing section/subsection (A's scheme: leaf id is
        book.subN.M.kindX -> parent book.subN.M; section nodes are their own)."""
        nid = h.node_id or ""
        if not nid.startswith("book.sub") and not nid.startswith("book.sec"):
            return None
        parts = nid.split(".")
        # book.sub7.5.theorem117 -> book.sub7.5 ; book.sub7.5 -> itself
        if len(parts) >= 4:
            return ".".join(parts[:3])
        return nid

    def _coarse_sections(self, query: str, qv, k: int = 3) -> set[str]:
        """Top-k section/subsection node_ids by vector+lexical, for coarse-to-fine."""
        qv = qv if qv is not None else self.embed(query)
        vrows = self._run(
            f"""select node_id, 1-(embedding <=> %s) sim
                from {SCHEMA}.c_chunks
                where level='section' and embedding is not null
                order by embedding <=> %s limit %s""", (qv, qv, k))
        return {r[0] for r in vrows}

    # -- LLM rerank (Claude) --
    def rerank(self, query: str, cands: list[Cand]) -> list[Cand]:
        from rerank import claude_rerank
        order, cost = claude_rerank(query, cands)
        self.rerank_cost = getattr(self, "rerank_cost", {"in": 0, "out": 0, "calls": 0})
        self.rerank_cost["in"] += cost.get("in", 0)
        self.rerank_cost["out"] += cost.get("out", 0)
        self.rerank_cost["calls"] += 1
        # reassign descending scores by the model's order; keep unranked at tail
        ranked = []
        n = len(order)
        for pos, idx in enumerate(order):
            if 0 <= idx < len(cands):
                c = cands[idx]
                c.score = 100.0 + (n - pos)  # dominate the fused score, preserve order
                c.signals = {**c.signals, "rerank_pos": pos}
                ranked.append(c)
        ranked_ids = {c.chunk_id for c in ranked}
        ranked += [c for c in cands if c.chunk_id not in ranked_ids]
        return ranked


# convenience: build a retrieve_fn bound to a live Retriever + a config
def make_retrieve_fn(r: "Retriever", **cfg):
    def fn(query: str, k: int) -> list[dict]:
        return [c.as_dict() for c in r.hybrid(query, k=k, **cfg)]
    return fn


def make_baseline_fn(r: "Retriever", mode: str = "vector"):
    def fn(query: str, k: int) -> list[dict]:
        cands = (r.baseline_vector(query, k) if mode == "vector"
                 else r.baseline_lexical(query, k))
        return [c.as_dict() for c in cands]
    return fn

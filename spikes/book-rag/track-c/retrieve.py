"""Track C — retrieval primitives + the first structure-aware hybrid (spec §13).

Three primitives, each over EITHER index table:
  (a) lexical  — tsv @@ plainto_tsquery + ts_rank
  (b) vector   — embedding <=> query_embedding (cosine distance)
  (c) hybrid   — normalized linear combo of (a) + (b) + a metadata/type boost

The type boost is the structure-aware signal: a query intent ("define X",
"state/prove theorem", "Theorem 7.7", "example/intuition") nudges results whose
`kind` matches the intent (spec §13 metadata/type boosts). The naive baseline
table has no `kind`/`label`/`heading_path`, so its hybrid is lexical+vector only
— which is exactly the comparison we want.

This R1 hybrid does NOT yet rerank with an LLM (that lands in R2 alongside D's
gold). The "reranker_score" term in the spec's formula is a stub here.
"""
from __future__ import annotations

import re
import sys
import time
import pathlib
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _shared.db import connect, SCHEMA  # noqa: E402
from embed import embed_one  # noqa: E402


@dataclass
class Hit:
    chunk_id: str
    node_id: str | None
    kind: str | None
    label: str | None
    heading_path: list[str] | None
    page: int | None
    text: str
    score: float
    signals: dict


# ---- intent → type boost map (spec §13) -----------------------------------
def intent_boosts(query: str) -> dict[str, float]:
    """Return a per-kind additive boost in [0, 1] from a light intent classifier.
    Deliberately simple/keyword-based for R1 — a real system would learn this."""
    q = query.lower()
    boosts: dict[str, float] = {}

    def add(kinds, w):
        for k in kinds:
            boosts[k] = max(boosts.get(k, 0.0), w)

    if re.search(r"\b(what is|define|definition of|meaning of)\b", q):
        add(["definition"], 1.0)
        add(["exposition", "remark"], 0.3)
    if re.search(r"\b(theorem|prove|proof|proposition|lemma|corollary|show that)\b", q):
        add(["theorem", "proposition", "lemma", "corollary"], 0.8)
        add(["proof"], 0.6)
    if re.search(r"\b(why|because|how do we know)\b", q):
        add(["proof", "lemma"], 0.7)
    if re.search(r"\b(example|intuition|illustrat|e\.g\.|for instance)\b", q):
        add(["example", "remark"], 0.9)
    if re.search(r"\b(problem|exercise)\b", q):
        add(["exercise"], 1.0)
    return boosts


# exact label like "Theorem 7.7", "Problem 7.x", "Proposition 7.1"
LABEL_IN_QUERY = re.compile(
    r"\b(theorem|proposition|lemma|corollary|definition|example|remark|exercise|problem)\s+(\d+(?:\.\w+)?)",
    re.I)


def label_target(query: str) -> str | None:
    m = LABEL_IN_QUERY.search(query)
    if not m:
        return None
    return f"{m.group(1).capitalize()} {m.group(2)}"


# ---- primitives -----------------------------------------------------------
def lexical(query: str, table: str, k: int = 10) -> list[Hit]:
    with connect() as conn, conn.cursor() as cur:
        if table == "c_chunks":
            cur.execute(
                f"""select chunk_id, node_id, kind, label, heading_path,
                          page_pdf_start, text,
                          ts_rank(tsv, plainto_tsquery('english', %s)) as r
                    from {SCHEMA}.c_chunks
                    where tsv @@ plainto_tsquery('english', %s)
                    order by r desc limit %s""", (query, query, k))
            return [Hit(r[0], r[1], r[2], r[3], r[4], r[5], r[6], float(r[7]),
                        {"lexical": float(r[7])}) for r in cur.fetchall()]
        else:
            cur.execute(
                f"""select chunk_id, page_pdf_start, text,
                          ts_rank(tsv, plainto_tsquery('english', %s)) as r
                    from {SCHEMA}.c_baseline_chunks
                    where tsv @@ plainto_tsquery('english', %s)
                    order by r desc limit %s""", (query, query, k))
            return [Hit(r[0], None, None, None, None, r[1], r[2], float(r[3]),
                        {"lexical": float(r[3])}) for r in cur.fetchall()]


def vector(query: str, table: str, k: int = 10, qvec: np.ndarray | None = None) -> list[Hit]:
    qv = qvec if qvec is not None else embed_one(query)
    with connect() as conn, conn.cursor() as cur:
        if table == "c_chunks":
            cur.execute(
                f"""select chunk_id, node_id, kind, label, heading_path,
                          page_pdf_start, text, 1 - (embedding <=> %s) as sim
                    from {SCHEMA}.c_chunks
                    where embedding is not null
                    order by embedding <=> %s limit %s""", (qv, qv, k))
            return [Hit(r[0], r[1], r[2], r[3], r[4], r[5], r[6], float(r[7]),
                        {"vector": float(r[7])}) for r in cur.fetchall()]
        else:
            cur.execute(
                f"""select chunk_id, page_pdf_start, text, 1 - (embedding <=> %s) as sim
                    from {SCHEMA}.c_baseline_chunks
                    where embedding is not null
                    order by embedding <=> %s limit %s""", (qv, qv, k))
            return [Hit(r[0], None, None, None, None, r[1], r[2], float(r[3]),
                        {"vector": float(r[3])}) for r in cur.fetchall()]


def _minmax(vals: dict[str, float]) -> dict[str, float]:
    if not vals:
        return {}
    lo, hi = min(vals.values()), max(vals.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in vals}
    return {k: (v - lo) / (hi - lo) for k, v in vals.items()}


def hybrid(query: str, table: str, k: int = 10,
           w_vec: float = 1.0, w_lex: float = 1.0, w_type: float = 0.6,
           w_label: float = 2.0, pool: int = 30,
           use_type: bool = True, use_label: bool = True) -> list[Hit]:
    """Normalized linear combo of lexical + vector + type/metadata boosts (§13).

    Ablation handles via use_type / use_label / weights so R2 can quantify which
    signal carries the weight. Candidate pool = union of lexical+vector top-`pool`.
    """
    qv = embed_one(query)
    lex = lexical(query, table, k=pool)
    vec = vector(query, table, k=pool, qvec=qv)

    lex_n = _minmax({h.chunk_id: h.score for h in lex})
    vec_n = _minmax({h.chunk_id: h.score for h in vec})

    by_id: dict[str, Hit] = {}
    for h in lex + vec:
        by_id.setdefault(h.chunk_id, h)

    boosts = intent_boosts(query) if use_type else {}
    tgt = label_target(query) if use_label else None

    scored: list[Hit] = []
    for cid, h in by_id.items():
        lv = lex_n.get(cid, 0.0)
        vv = vec_n.get(cid, 0.0)
        type_b = boosts.get(h.kind, 0.0) if (use_type and h.kind) else 0.0
        label_b = 0.0
        if use_label and tgt and h.label and h.label.lower() == tgt.lower():
            label_b = 1.0
        final = w_vec * vv + w_lex * lv + w_type * type_b + w_label * label_b
        sig = {"vector_n": round(vv, 3), "lexical_n": round(lv, 3),
               "type_boost": type_b, "label_boost": label_b}
        scored.append(Hit(h.chunk_id, h.node_id, h.kind, h.label, h.heading_path,
                          h.page, h.text, final, sig))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:k]


def search(query: str, mode: str, table: str, k: int = 10, **kw) -> tuple[list[Hit], float]:
    """Dispatch + time a single query. mode in {lexical, vector, hybrid}."""
    t0 = time.time()
    if mode == "lexical":
        hits = lexical(query, table, k)
    elif mode == "vector":
        hits = vector(query, table, k)
    elif mode == "hybrid":
        hits = hybrid(query, table, k, **kw)
    else:
        raise ValueError(mode)
    return hits, time.time() - t0

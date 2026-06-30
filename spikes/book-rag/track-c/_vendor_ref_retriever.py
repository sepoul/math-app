"""Track D R2 — a REFERENCE retriever, used only to exercise the measuring stick
on the real corpus and produce verdict numbers BEFORE Track C publishes its own
d_results. This is NOT Track C's deliverable and not the recommended system; it
is a measurement instrument so the stick reports real numbers, not mocks. When
C's runs land in d_results, we re-score those (harness.score against d_gold) and
these reference numbers are superseded.

It retrieves over the LIVE tables Track C already built:
  * c_chunks          — structure-aware units (section + leaf), with tsv + 1536-d
                        embedding + label + heading_path + kind. Used by the
                        structured-hybrid variants + ablations.
  * c_baseline_chunks — fixed-window page chunks, embedding only, NO label / NO
                        heading_path. Used by the naive baseline.

Variants (run_labels), all scored on the same d_gold:
  refD_structured_hybrid   lexical(FTS) + vector + type-boost, fused
  refD_no_vector           lexical + type-boost          (vector ablated)
  refD_no_lexical          vector + type-boost           (lexical ablated)
  refD_no_type_boost       lexical + vector              (type-boost ablated)
  refD_naive_baseline      vector over fixed-window chunks (no structure/label)

Matching to gold is by LABEL (C's chunk node_ids are in C's own c.tu.* namespace,
not A's book.* ids — a seam mismatch recorded in FINDINGS). Labels align exactly,
so scoring is sound; node_id-level matching activates once C emits A's ids.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import connect, SCHEMA, load_env  # noqa: E402

EMBED_MODEL = "text-embedding-3-small"   # 1536-d, matches C's index
_client = None
_embed_calls = {"n": 0, "tokens": 0}


def _openai():
    global _client
    if _client is None:
        from openai import OpenAI
        os.environ.setdefault("OPENAI_API_KEY", load_env()["OPENAI_API_KEY"])
        _client = OpenAI()
    return _client


def embed(text: str) -> list[float]:
    r = _openai().embeddings.create(model=EMBED_MODEL, input=text)
    _embed_calls["n"] += 1
    _embed_calls["tokens"] += r.usage.total_tokens
    return r.data[0].embedding


# ----- type/intent boost: map the query to the structural roles it wants ----- #
def type_boost_kinds(query: str) -> set[str]:
    q = query.lower()
    if q.startswith(("theorem", "proposition", "lemma", "corollary")) or "theorem" in q:
        return {"theorem", "proposition", "lemma", "corollary"}
    if "definition" in q or q.startswith("what is") or q.startswith("define"):
        return {"definition", "section", "subsection"}
    if "proof" in q or q.startswith("why"):
        return {"proof", "lemma"}
    if "example" in q or "intuition" in q or "gluing" in q:
        return {"example", "remark"}
    return set()


def _vector_scores(cur, table: str, qvec, k: int):
    cur.execute(
        f"""select chunk_id, node_id, label, kind, page_pdf_start, heading_path,
                   1 - (embedding <=> %s::vector) as sim
            from {SCHEMA}.{table}
            where embedding is not null
            order by embedding <=> %s::vector limit %s;""",
        (qvec, qvec, k))
    return cur.fetchall()


def _baseline_vector_scores(cur, qvec, k: int):
    # c_baseline_chunks is a flat fixed-window index: no node_id/label/kind/heading.
    cur.execute(
        f"""select chunk_id, page_pdf_start, 1 - (embedding <=> %s::vector) as sim
            from {SCHEMA}.c_baseline_chunks
            where embedding is not null
            order by embedding <=> %s::vector limit %s;""",
        (qvec, qvec, k))
    return cur.fetchall()


def _lexical_scores(cur, query: str, k: int):
    cur.execute(
        f"""select chunk_id, node_id, label, kind, page_pdf_start, heading_path,
                   ts_rank(tsv, plainto_tsquery('english', %s)) as r
            from {SCHEMA}.c_chunks
            where tsv @@ plainto_tsquery('english', %s)
            order by r desc limit %s;""",
        (query, query, k))
    return cur.fetchall()


def _norm_scores(rows, idx):
    vals = [r[idx] for r in rows] or [0]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    return {r[0]: (r[idx] - lo) / span for r in rows}


def make_retriever(variant: str):
    """Return retrieve_fn(query_text, k) -> list[dict] for harness.evaluate."""
    use_vec = variant not in ("refD_no_vector",)
    use_lex = variant not in ("refD_no_lexical",)
    use_boost = variant not in ("refD_no_type_boost", "refD_naive_baseline")
    naive = variant == "refD_naive_baseline"

    def retrieve(query_text: str, k: int):
        qvec = embed(query_text)
        with connect() as c, c.cursor() as cur:
            if naive:
                rows = _baseline_vector_scores(cur, qvec, k)
                out = []
                for r in rows:
                    out.append({"chunk_id": r[0], "node_id": None, "score": float(r[2]),
                                "label": None, "page_pdf_start": r[1],
                                "heading_path": None,  # baseline has no hierarchy
                                "signals": {"vector": float(r[2]), "page_pdf_start": r[1]}})
                return out

            pool: dict[str, dict] = {}
            vec_rows = _vector_scores(cur, "c_chunks", qvec, 30) if use_vec else []
            lex_rows = _lexical_scores(cur, query_text, 30) if use_lex else []
            vnorm = _norm_scores(vec_rows, 6) if vec_rows else {}
            lnorm = _norm_scores(lex_rows, 6) if lex_rows else {}
            for rows in (vec_rows, lex_rows):
                for r in rows:
                    cid = r[0]
                    # C re-indexed onto A's book.* node_id namespace (chunk_id is
                    # c.struct.<node_id>, node_id column == A's id) -> emit the real
                    # node_id so the matcher scores on EXACT node_id (label kept too).
                    d = pool.setdefault(cid, {"chunk_id": cid, "node_id": r[1],
                                              "label": r[2],
                                              "kind": r[3], "page_pdf_start": r[4],
                                              "heading_path": r[5], "signals": {}})
            boost_kinds = type_boost_kinds(query_text) if use_boost else set()
            for cid, d in pool.items():
                vs = vnorm.get(cid, 0.0)
                ls = lnorm.get(cid, 0.0)
                tb = 0.25 if (d["kind"] in boost_kinds) else 0.0
                d["signals"] = {"vector": round(vs, 4), "lexical": round(ls, 4),
                                "type_boost": tb, "kind": d["kind"],
                                "label": d["label"], "page_pdf_start": d["page_pdf_start"],
                                "heading_path": d["heading_path"]}
                d["score"] = round(0.5 * vs + 0.5 * ls + tb, 4)
            ranked = sorted(pool.values(), key=lambda x: -x["score"])[:k]
            for d in ranked:
                d.pop("kind", None)
            return ranked

    return retrieve


def embed_usage():
    return dict(_embed_calls)

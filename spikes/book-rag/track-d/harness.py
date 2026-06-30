"""Track D — eval harness scaffold.

Two jobs:
  1. `load_queries()` / `load_gold()` — read the file-mirror (queries/*.json) into
     the `metrics` dataclasses, so any track can score without touching the DB.
  2. `evaluate(retrieve_fn, run_label, ...)` — the scaffold Track C calls in R2:
     given a retrieval function, it runs every query, TIMES it, scores the run
     against gold, and (optionally) persists d_results + d_speed_cost rows.

The `d_results` run convention (mirrors the d_results table)
------------------------------------------------------------
One row per (run_label, query_id, rank) retrieved item:
    run_label            free-text run id, e.g. "hybrid_full", "naive_baseline",
                         "hybrid_no_rerank" (use for the C ablation).
    query_id             FK to d_queries.
    rank                 1-based rank of this item in the result list.
    retrieved_node_id    a_nodes.node_id once A lands (else null).
    retrieved_chunk_id   c_chunks.chunk_id (the retriever's own unit).
    score                the retriever's fused score for this item.
    signals              jsonb: per-signal contributions for the §17 ablation,
                         e.g. {"lexical":0.4,"vector":0.3,"type_boost":0.2,
                         "rerank":0.9,"label":"Theorem 7.7","page_pdf_start":94,
                         "heading_path":["Chapter 2: Manifolds","§7 Quotients",
                         "7.5 Open Equivalence Relations"]}.
    NOTE: label/page_pdf_start/heading_path live inside `signals` so traceability
    + label matching survive the round-1 (no node_id) reality. The harness pulls
    them back out into RetrievedItem for scoring.

The retrieval function contract (what C implements)
---------------------------------------------------
    retrieve_fn(query_text: str, k: int) -> list[dict]
where each dict carries any of:
    node_id, chunk_id, score, label, page_pdf_start, heading_path, signals
Rank is assigned by list order (0 -> rank 1). The harness is retriever-agnostic;
it never inspects the index, only the returned candidates.
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import Any, Callable, Optional

from metrics import GoldItem, RetrievedItem, RunReport, score_run

QUERIES_DIR = pathlib.Path(__file__).resolve().parents[1] / "queries"


# --------------------------------------------------------------------------- #
# Loaders (file-mirror -> dataclasses)
# --------------------------------------------------------------------------- #
def load_queries(path: Optional[pathlib.Path] = None) -> dict[str, dict[str, str]]:
    """query_id -> {category, query_text, intent}."""
    data = json.loads((path or QUERIES_DIR / "queries.json").read_text())
    return {q["query_id"]: {"category": q["category"], "query_text": q["query_text"],
                            "intent": q.get("intent", "")} for q in data["queries"]}


def load_gold(path: Optional[pathlib.Path] = None) -> dict[str, list[GoldItem]]:
    """query_id -> [GoldItem]."""
    data = json.loads((path or QUERIES_DIR / "gold.json").read_text())
    out: dict[str, list[GoldItem]] = {}
    for qid, items in data["gold"].items():
        out[qid] = [GoldItem(query_id=qid, gold_label=it.get("gold_label"),
                             gold_node_id=it.get("gold_node_id"),
                             relevance=int(it.get("relevance", 1)),
                             rationale=it.get("rationale", ""),
                             page_pdf=it.get("page_pdf")) for it in items]
    return out


def category_map(queries: dict[str, dict[str, str]]) -> dict[str, str]:
    return {qid: q["category"] for qid, q in queries.items()}


# --------------------------------------------------------------------------- #
# Candidate -> RetrievedItem (normalize the retriever's dict contract)
# --------------------------------------------------------------------------- #
def _to_item(qid: str, rank: int, cand: dict[str, Any]) -> RetrievedItem:
    sig = dict(cand.get("signals") or {})
    label = cand.get("label", sig.get("label"))
    page = cand.get("page_pdf_start", sig.get("page_pdf_start"))
    heading = cand.get("heading_path", sig.get("heading_path"))
    return RetrievedItem(
        query_id=qid, rank=rank,
        retrieved_node_id=cand.get("node_id"),
        retrieved_chunk_id=cand.get("chunk_id"),
        score=cand.get("score"),
        label=label, page_pdf_start=page, heading_path=heading, signals=sig,
    )


# --------------------------------------------------------------------------- #
# The evaluate scaffold (what C calls in R2)
# --------------------------------------------------------------------------- #
def evaluate(
    retrieve_fn: Callable[[str, int], list[dict[str, Any]]],
    run_label: str,
    *,
    k: int = 10,
    persist: bool = False,
    match_mode: str = "auto",
    queries: Optional[dict[str, dict[str, str]]] = None,
    gold: Optional[dict[str, list[GoldItem]]] = None,
) -> tuple[RunReport, dict[str, list[RetrievedItem]], dict[str, float]]:
    """Run every query through `retrieve_fn`, time it, score it, optionally write
    d_results + d_speed_cost. Returns (report, results_by_query, latency_ms_by_query).
    match_mode='page' scores label-less retrievers fairly (see metrics.score_run)."""
    queries = queries or load_queries()
    gold = gold or load_gold()
    catmap = category_map(queries)

    results_by_query: dict[str, list[RetrievedItem]] = {}
    latency_ms: dict[str, float] = {}
    raw_candidates: dict[str, list[dict[str, Any]]] = {}

    for qid, q in queries.items():
        t0 = time.perf_counter()
        cands = retrieve_fn(q["query_text"], k) or []
        latency_ms[qid] = (time.perf_counter() - t0) * 1000.0
        raw_candidates[qid] = cands
        results_by_query[qid] = [_to_item(qid, i + 1, c) for i, c in enumerate(cands[:k])]

    report = score_run(run_label, results_by_query, gold, catmap, match_mode=match_mode)

    if persist:
        _persist(run_label, raw_candidates, latency_ms, report)
    return report, results_by_query, latency_ms


# --------------------------------------------------------------------------- #
# Persistence (d_results + d_speed_cost). Imported lazily so the metrics half
# of the harness has no DB dependency.
# --------------------------------------------------------------------------- #
def _persist(run_label, raw_candidates, latency_ms, report: RunReport) -> None:
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from _shared.db import connect, SCHEMA  # noqa: E402

    with connect() as conn, conn.cursor() as cur:
        # idempotent on (run_label): clear prior rows for this label first
        cur.execute(f"delete from {SCHEMA}.d_results where run_label=%s;", (run_label,))
        cur.execute(f"delete from {SCHEMA}.d_speed_cost where run_label=%s;", (run_label,))
        for qid, cands in raw_candidates.items():
            for rank, c in enumerate(cands, start=1):
                cur.execute(
                    f"""insert into {SCHEMA}.d_results
                        (run_label, query_id, rank, retrieved_node_id,
                         retrieved_chunk_id, score, signals)
                        values (%s,%s,%s,%s,%s,%s,%s)""",
                    (run_label, qid, rank, c.get("node_id"), c.get("chunk_id"),
                     c.get("score"), json.dumps(_signals_for(c))))
        # latency ledger (per query) + an aggregate
        lat = sorted(latency_ms.values())
        if lat:
            p50 = lat[len(lat) // 2]
            p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
            mean = sum(lat) / len(lat)
            for metric, val in [("query_latency_p50_ms", p50),
                                ("query_latency_p95_ms", p95),
                                ("query_latency_mean_ms", mean)]:
                cur.execute(
                    f"""insert into {SCHEMA}.d_speed_cost (stage, run_label, metric, value, detail)
                        values (%s,%s,%s,%s,%s)""",
                    ("query", run_label, metric, val,
                     json.dumps({"n_queries": len(lat)})))
        # stamp headline quality so the ledger is self-contained
        for metric, val in report.macro.items():
            cur.execute(
                f"""insert into {SCHEMA}.d_speed_cost (stage, run_label, metric, value, detail)
                    values (%s,%s,%s,%s,%s)""",
                ("quality", run_label, metric,
                 None if val != val else float(val), json.dumps({"source": "score_run"})))
        conn.commit()


def _signals_for(cand: dict[str, Any]) -> dict[str, Any]:
    """Fold label/page/heading into signals so d_results stays self-describing."""
    sig = dict(cand.get("signals") or {})
    for fld in ("label", "page_pdf_start", "heading_path"):
        if cand.get(fld) is not None and fld not in sig:
            sig[fld] = cand[fld]
    return sig


# --------------------------------------------------------------------------- #
# DB loaders for d_queries / d_gold (so C can also read gold straight from the
# shared tables instead of the file-mirror, whichever it prefers).
# --------------------------------------------------------------------------- #
def load_gold_from_db() -> dict[str, list[GoldItem]]:
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from _shared.db import connect, SCHEMA  # noqa: E402
    out: dict[str, list[GoldItem]] = {}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"""select query_id, gold_node_id, gold_label, relevance, rationale, page_pdf
                        from {SCHEMA}.d_gold order by query_id;""")
        for qid, nid, lbl, rel, rat, page in cur.fetchall():
            out.setdefault(qid, []).append(
                GoldItem(query_id=qid, gold_node_id=nid, gold_label=lbl,
                         relevance=rel or 1, rationale=rat or "", page_pdf=page))
    return out


__all__ = ["load_queries", "load_gold", "category_map", "evaluate",
           "load_gold_from_db"]

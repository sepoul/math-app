"""Track D R2 — turn the stick into numbers.

1. Run the reference retriever variants over the live c_chunks / c_baseline_chunks.
2. Score each against d_gold (recall@k, MRR, nDCG, exact-label-hit, traceability).
3. Persist d_results + d_speed_cost (per-query latency + embedding token/$).
4. Print the head-to-head comparison + the per-signal ablation.

(When Track C publishes its OWN d_results, call score_existing_run(run_label) to
score those directly off the d_results table — same metrics, no retriever needed.)
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harness import evaluate, load_gold, load_queries, category_map  # noqa: E402
from metrics import RetrievedItem, score_run                           # noqa: E402
import ref_retriever as rr                                             # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import connect, SCHEMA                                 # noqa: E402

# text-embedding-3-small list price (USD / 1M tokens), for the cost ledger.
EMBED_USD_PER_MTOK = 0.02

VARIANTS = [
    "refD_structured_hybrid",
    "refD_no_vector",
    "refD_no_lexical",
    "refD_no_type_boost",
    "refD_naive_baseline",
]


def run_all(persist: bool = True):
    reports = {}
    for v in VARIANTS:
        # naive baseline carries no label/node_id -> score by page-overlap so it
        # gets fair credit on the same gold (coordinator: keep page-range gold).
        mode = "page" if v == "refD_naive_baseline" else "auto"
        t0 = time.perf_counter()
        rr._embed_calls.update(n=0, tokens=0)
        rep, results, lat = evaluate(rr.make_retriever(v), v, k=10, persist=persist,
                                     match_mode=mode)
        wall = time.perf_counter() - t0
        usage = rr.embed_usage()
        reports[v] = rep
        if persist:
            _write_cost(v, lat, usage, wall)
        print("=" * 64)
        print(rep.summary_table(), f"  [match_mode={mode}]")
        print(f"embed: {usage['n']} calls, {usage['tokens']} tok, "
              f"${usage['tokens']/1e6*EMBED_USD_PER_MTOK:.6f} | wall {wall:.1f}s")
        print()
    # apples-to-apples: also score structured_hybrid on page-overlap, so the
    # hybrid-vs-naive gap isn't an artifact of different match modes.
    rep_hp, _, _ = evaluate(rr.make_retriever("refD_structured_hybrid"),
                            "refD_structured_hybrid_pagematch", k=10,
                            persist=False, match_mode="page")
    reports["refD_structured_hybrid_pagematch"] = rep_hp
    print("=" * 64)
    print("refD_structured_hybrid scored on PAGE-overlap (apples-to-apples vs naive):")
    print(rep_hp.summary_table())
    print()
    _comparison(reports)
    return reports


def _write_cost(run_label, lat, usage, wall):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"delete from {SCHEMA}.d_speed_cost where run_label=%s and stage in ('query','cost');", (run_label,))
        lats = sorted(lat.values())
        p50 = lats[len(lats)//2]
        p95 = lats[min(len(lats)-1, int(len(lats)*0.95))]
        mean = sum(lats)/len(lats)
        tok = usage["tokens"]
        n = max(1, usage["n"])
        rows = [
            ("query", "query_latency_p50_ms", p50, {"n": len(lats)}),
            ("query", "query_latency_p95_ms", p95, {"n": len(lats)}),
            ("query", "query_latency_mean_ms", mean, {"n": len(lats)}),
            ("cost", "embed_tokens_total", float(tok), {"model": rr.EMBED_MODEL}),
            ("cost", "embed_tokens_per_query", tok / n, {}),
            ("cost", "embed_usd_per_query", tok / n / 1e6 * EMBED_USD_PER_MTOK, {"price_per_mtok": EMBED_USD_PER_MTOK}),
            ("query", "wall_seconds_total", wall, {"n_queries": n}),
        ]
        for stage, metric, val, detail in rows:
            cur.execute(
                f"insert into {SCHEMA}.d_speed_cost (stage, run_label, metric, value, detail) values (%s,%s,%s,%s,%s)",
                (stage, run_label, metric, float(val), json.dumps(detail)))
        conn.commit()


def _comparison(reports):
    print("#" * 64)
    print("HEAD-TO-HEAD (macro over 26 queries)")
    cols = ["recall@1", "recall@5", "recall@10", "mrr", "ndcg@5", "exact_label_hit_rate", "traceability"]
    hdr = f"{'run_label':<34}" + "".join(f"{c:>14}" for c in cols)
    print(hdr)
    order = VARIANTS + ["refD_structured_hybrid_pagematch"]
    for v in order:
        if v not in reports:
            continue
        m = reports[v].macro
        print(f"{v:<34}" + "".join(f"{m.get(c, float('nan')):>14.3f}" for c in cols))
    # ablation deltas vs full hybrid
    print("\nABLATION Δ vs refD_structured_hybrid (recall@5 / ndcg@5):")
    base = reports["refD_structured_hybrid"].macro
    for v in VARIANTS:
        if v == "refD_structured_hybrid":
            continue
        m = reports[v].macro
        print(f"  {v:<24} Δrecall@5={m['recall@5']-base['recall@5']:+.3f}  "
              f"Δndcg@5={m['ndcg@5']-base['ndcg@5']:+.3f}")
    # per-category for the headline run
    print("\nrefD_structured_hybrid by category:")
    print(reports["refD_structured_hybrid"].summary_table().split("\n", 1)[1].rsplit("\n\n", 1)[0])


def score_existing_run(run_label: str):
    """Score a run already present in d_results (e.g. Track C's) off the table."""
    gold = load_gold(); queries = load_queries(); catmap = category_map(queries)
    by_q: dict[str, list[RetrievedItem]] = {}
    with connect() as c, c.cursor() as cur:
        cur.execute(f"""select query_id, rank, retrieved_node_id, retrieved_chunk_id, score, signals
                        from {SCHEMA}.d_results where run_label=%s order by query_id, rank;""", (run_label,))
        for qid, rank, nid, cid, score, sig in cur.fetchall():
            sig = sig or {}
            by_q.setdefault(qid, []).append(RetrievedItem(
                query_id=qid, rank=rank, retrieved_node_id=nid, retrieved_chunk_id=cid,
                score=score, label=sig.get("label"), page_pdf_start=sig.get("page_pdf_start"),
                heading_path=sig.get("heading_path"), signals=sig))
    rep = score_run(run_label, by_q, gold, catmap)
    print(rep.summary_table())
    return rep


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--score-existing":
        score_existing_run(sys.argv[2])
    else:
        run_all(persist="--no-persist" not in sys.argv)

"""Track C — R4 FINAL: score the LOCKED C_full config + final numbers.

Scores the single locked config (retrieve_r2.C_FULL_CFG / c_full_retrieve_fn) on
A's frozen corpus against FILE gold, under BOTH match rules:
  * strict  — exact unit (node_id -> label only; no page credit)
  * auto    — node_id -> label -> page fallback (the headline / honest)
plus the naive baseline (page mode) for the standing comparison.

Reports strict + auto recall@5/@10, MRR, exact-label-hit, source-traceability,
and p50/p95 latency + per-query $ (rerank). Persists the locked run to d_results.

Also runs a small ceiling A/B: C_full at the locked POOL vs pool=30, strict
recall, to show whether widening the pool lifted the strict ceiling.
"""
from __future__ import annotations

import sys
import time
import pathlib
import importlib.util

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))


def _load(n, f):
    s = importlib.util.spec_from_file_location(n, HERE / f)
    m = importlib.util.module_from_spec(s); sys.modules[n] = m; s.loader.exec_module(m); return m


metrics = _load("metrics", "_vendor_metrics.py")
harness = _load("harness", "_vendor_harness.py")
from retrieve_r2 import (Retriever, make_retrieve_fn, make_baseline_fn,  # noqa: E402
                         c_full_retrieve_fn, C_FULL_CFG, POOL)


def pctl(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else float("nan")


def main():
    queries = harness.load_queries(HERE / "_vendor_queries.json")
    gold = harness.load_gold(HERE / "_vendor_gold.json")
    r = Retriever()

    fn = c_full_retrieve_fn(r)
    reps = {}
    lat = {}
    # locked C_full under strict + auto (same retrieval, two match rules; persist auto)
    for mode in ("strict", "auto"):
        t0 = time.time()
        rep, _, l = harness.evaluate(fn, "C_full", k=10,
                                     persist=(mode == "auto"),
                                     queries=queries, gold=gold, match_mode=mode)
        reps[mode] = rep
        if mode == "auto":
            lat = l
    # naive baseline (page mode) for the standing comparison
    nb, _, nl = harness.evaluate(make_baseline_fn(r, "vector"), "naive_baseline", k=10,
                                 persist=True, queries=queries, gold=gold, match_mode="page")

    print("=" * 92)
    print("LOCKED C_full — FINAL NUMBERS (frozen corpus track-a-r1, file gold, 26 queries)")
    print("=" * 92)
    print(f"  locked config: pool={C_FULL_CFG['pool']}, lexical+vector+type+label, "
          f"intent-gated graph, coarse-to-fine, rerank(pool={C_FULL_CFG['rerank_pool']})")
    cols = ["recall@5", "recall@10", "mrr", "ndcg@5", "exact_label_hit_rate", "traceability"]
    print(f"\n{'scoring':<22}" + "".join(f"{c.replace('_hit_rate','_hit'):>14}" for c in cols))
    for mode in ("strict", "auto"):
        m = reps[mode].macro
        print(f"  C_full [{mode:<6}]      " + "".join(f"{m.get(c, float('nan')):>14.3f}" for c in cols))
    mb = nb.macro
    print(f"  naive_baseline[page] " + "".join(f"{mb.get(c, float('nan')):>14.3f}" for c in cols))

    lats = list(lat.values())
    print(f"\nLATENCY (C_full incl. rerank): p50={pctl(lats,0.5):.0f}ms  "
          f"p95={pctl(lats,0.95):.0f}ms  mean={sum(lats)/len(lats):.0f}ms")
    rc = getattr(r, "rerank_cost", None)
    if rc:
        cost = rc['in'] * 1.0/1e6 + rc['out'] * 5.0/1e6
        print(f"COST: embeddings {r.embed_calls} calls ({1000*r.embed_seconds/max(r.embed_calls,1):.0f}ms/call, cached); "
              f"rerank {rc['calls']} calls ~${cost:.4f} total (~${cost/max(rc['calls'],1):.5f}/query, claude-haiku-4-5)")

    # --- ceiling A/B: widened pool vs pool=30, STRICT recall ---
    print("\n" + "-" * 60)
    print("STRICT-RECALL CEILING A/B (recall@5/@10 under strict match):")
    for pool in (30, POOL):
        cfg = {**C_FULL_CFG, "pool": pool, "rerank": False}  # isolate pool effect, no rerank noise
        ab_fn = make_retrieve_fn(r, **cfg)
        rep, _, _ = harness.evaluate(ab_fn, f"ab_pool{pool}", k=10, persist=False,
                                     queries=queries, gold=gold, match_mode="strict")
        m = rep.macro
        print(f"  pool={pool:<3} (no rerank)  strict recall@5={m['recall@5']:.3f}  recall@10={m['recall@10']:.3f}")
    # and with rerank at locked pool
    rep, _, _ = harness.evaluate(fn, "ab_full_strict", k=10, persist=False,
                                 queries=queries, gold=gold, match_mode="strict")
    m = rep.macro
    print(f"  pool={POOL} + rerank      strict recall@5={m['recall@5']:.3f}  recall@10={m['recall@10']:.3f}")
    r.close()


if __name__ == "__main__":
    main()

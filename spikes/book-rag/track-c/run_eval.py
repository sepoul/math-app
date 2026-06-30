"""Track C — R2 scored bake-off + ablation + rerank, via Track D's harness.

Drives Track D's `evaluate(retrieve_fn, run_label, persist=True)` across:
  baseline:           naive_baseline (vector over c_baseline_chunks)
  structured paths:   lexical_only, vector_only, +type_boost, hybrid_full,
                      +graph_expansion, +rerank
We score against D's gold (read from the shared d_gold table via the harness's
load_gold_from_db) so C does not invent metrics. Persists d_results + d_speed_cost
per run_label. Prints the head-to-head + ablation tables + warm latency.

D's harness module lives on D's branch; we vendor a copy (track-c/_vendor_*).
"""
from __future__ import annotations

import sys
import time
import json
import pathlib
import importlib.util

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))


def _load_vendor(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# metrics must import first (harness does `from metrics import ...`)
metrics = _load_vendor("metrics", "_vendor_metrics.py")
harness = _load_vendor("harness", "_vendor_harness.py")

from retrieve_r2 import Retriever, make_retrieve_fn, make_baseline_fn  # noqa: E402


def load_queries_gold():
    """queries from the vendored file; gold from the shared d_gold table."""
    queries = harness.load_queries(HERE / "_vendor_queries.json")
    gold = harness.load_gold_from_db()  # authoritative shared table
    return queries, gold


# run configs: (run_label, kind, kwargs)
STRUCT_RUNS = [
    ("lexical_only",     dict(use_lexical=True,  use_vector=False, use_type=False, use_label=False, use_graph=False)),
    ("vector_only",      dict(use_lexical=False, use_vector=True,  use_type=False, use_label=False, use_graph=False)),
    ("lex_vec",          dict(use_lexical=True,  use_vector=True,  use_type=False, use_label=False, use_graph=False)),
    ("+type_boost",      dict(use_lexical=True,  use_vector=True,  use_type=True,  use_label=False, use_graph=False)),
    ("hybrid_full",      dict(use_lexical=True,  use_vector=True,  use_type=True,  use_label=True,  use_graph=False)),
    ("+graph_expansion", dict(use_lexical=True,  use_vector=True,  use_type=True,  use_label=True,  use_graph=True)),
    ("+rerank",          dict(use_lexical=True,  use_vector=True,  use_type=True,  use_label=True,  use_graph=True, rerank=True)),
]


def main():
    queries, gold = load_queries_gold()
    catmap = harness.category_map(queries)
    r = Retriever()
    reports = {}

    # naive baseline (vector + lexical)
    for label, mode in [("naive_baseline", "vector"), ("naive_lexical", "lexical")]:
        t0 = time.time()
        fn = make_baseline_fn(r, mode=mode)
        rep, _, lat = harness.evaluate(fn, label, k=10, persist=True, queries=queries, gold=gold)
        reports[label] = (rep, lat)
        print(f"[run] {label:<18} done in {time.time()-t0:.1f}s "
              f"recall@5={rep.macro['recall@5']:.3f}", flush=True)

    # structured runs
    for label, kw in STRUCT_RUNS:
        t0 = time.time()
        fn = make_retrieve_fn(r, **kw)
        rep, _, lat = harness.evaluate(fn, label, k=10, persist=True, queries=queries, gold=gold)
        reports[label] = (rep, lat)
        print(f"[run] {label:<18} done in {time.time()-t0:.1f}s "
              f"recall@5={rep.macro['recall@5']:.3f}", flush=True)

    r.close()

    # ---- headline table ----
    print("\n" + "=" * 92)
    print("HEAD-TO-HEAD  (scored on D's gold, k=10; macro means over 26 queries)")
    print("=" * 92)
    hdr = f"{'run_label':<18}{'recall@5':>9}{'mrr':>7}{'ndcg@5':>8}{'exact_lbl':>10}{'trace':>7}{'p50ms':>8}"
    print(hdr)
    order = ["naive_baseline", "naive_lexical", "lexical_only", "vector_only",
             "lex_vec", "+type_boost", "hybrid_full", "+graph_expansion", "+rerank"]
    for label in order:
        rep, lat = reports[label]
        m = rep.macro
        lats = sorted(lat.values())
        p50 = lats[len(lats) // 2] if lats else float("nan")
        print(f"{label:<18}{m['recall@5']:>9.3f}{m['mrr']:>7.3f}{m['ndcg@5']:>8.3f}"
              f"{m['exact_label_hit_rate']:>10.3f}{m['traceability']:>7.3f}{p50:>8.0f}")

    # ---- ablation deltas vs hybrid_full ----
    print("\n" + "-" * 60)
    print("ABLATION (Δ vs hybrid_full; negative = signal helps)")
    base = reports["hybrid_full"][0].macro
    for label in ["lexical_only", "vector_only", "lex_vec", "+type_boost", "+graph_expansion", "+rerank"]:
        m = reports[label][0].macro
        print(f"  {label:<18} Δrecall@5={m['recall@5']-base['recall@5']:+.3f}  "
              f"Δmrr={m['mrr']-base['mrr']:+.3f}  Δndcg@5={m['ndcg@5']-base['ndcg@5']:+.3f}")

    # ---- per-category for the two headline systems ----
    print("\n" + "-" * 60)
    print("BY CATEGORY (recall@5 | mrr): naive_baseline vs hybrid_full vs +rerank")
    for cat in ["direct", "conceptual", "structural", "graph_expansion"]:
        nb = reports["naive_baseline"][0].by_category.get(cat, {})
        hf = reports["hybrid_full"][0].by_category.get(cat, {})
        rr = reports["+rerank"][0].by_category.get(cat, {})
        print(f"  {cat:<16} naive {nb.get('recall@5',float('nan')):.2f}/{nb.get('mrr',float('nan')):.2f}   "
              f"hybrid {hf.get('recall@5',float('nan')):.2f}/{hf.get('mrr',float('nan')):.2f}   "
              f"+rerank {rr.get('recall@5',float('nan')):.2f}/{rr.get('mrr',float('nan')):.2f}")

    # ---- speed/cost ----
    print("\n" + "-" * 60)
    print("SPEED / COST")
    print(f"  query embeddings: {r.embed_calls} API calls, {r.embed_seconds:.2f}s total "
          f"({1000*r.embed_seconds/max(r.embed_calls,1):.0f} ms/call)")
    rc = getattr(r, "rerank_cost", None)
    if rc:
        cost = rc['in']*1.0/1e6 + rc['out']*5.0/1e6  # haiku-4-5 $1/$5 per MTok
        print(f"  rerank (claude-haiku-4-5): {rc['calls']} calls, "
              f"{rc['in']} in + {rc['out']} out tokens, ~${cost:.4f} for {rc['calls']} queries "
              f"(~${cost/max(rc['calls'],1):.5f}/query)")


if __name__ == "__main__":
    main()

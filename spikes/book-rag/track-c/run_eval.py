"""Track C — R3 RECONCILED bake-off + retrieval-depth, via Track D's harness.

The ONE agreed scorer: Track D's CURRENT harness/metrics (vendored from
origin/spike/eval-efficiency), `match_mode="auto"` (node_id -> label -> page
fallback). Scored on A's FROZEN corpus (rebuild c_chunks from a_nodes first).

Reconciliation (top priority): score C's retriever AND D's reference retriever on
the SAME scorer + SAME corpus, side by side, so the headline is one agreed number.

Runs (all persisted to d_results / d_speed_cost under match_mode=auto):
  naive_baseline           naive vector (label-less; auto falls back to page)
  D_ref_hybrid             D's reference retriever (lex+vec+0.25 type, 0.5/0.5)
  C_hybrid                 C's hybrid (lex+vec, min-max, type+label boost)
  C_hybrid+graph_gated     + intent-gated graph expansion (structural only)
  C_hybrid+coarse_to_fine  + section-first coarse-to-fine (§12)
  C_hybrid+rerank          + LLM rerank (latency-tuned)
  C_full (graph+cf+rerank) everything
"""
from __future__ import annotations

import sys
import time
import pathlib
import importlib.util

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, HERE / fn)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m
    spec.loader.exec_module(m); return m


metrics = _load("metrics", "_vendor_metrics.py")
harness = _load("harness", "_vendor_harness.py")
refret = _load("refret", "_vendor_ref_retriever.py")

from retrieve_r2 import Retriever, make_retrieve_fn, make_baseline_fn  # noqa: E402

MATCH = "auto"  # the agreed match rule: node_id -> label -> page fallback


def main():
    queries = harness.load_queries(HERE / "_vendor_queries.json")
    # Gold from D's file-mirror (NOT load_gold_from_db): the file carries `page_pdf`
    # on every item, which `load_gold_from_db` drops — without it the page fallback
    # in match_mode='auto'/'page' can never fire (this was why the label-less
    # baseline scored 0). node_ids/labels are identical to the DB gold, so the
    # structured (node_id-matched) numbers are unchanged.
    gold = harness.load_gold(HERE / "_vendor_gold.json")
    r = Retriever()
    reps = {}

    def run(label, fn, persist=True, match_mode=MATCH):
        t0 = time.time()
        rep, _, lat = harness.evaluate(fn, label, k=10, persist=persist,
                                       queries=queries, gold=gold, match_mode=match_mode)
        reps[label] = (rep, lat)
        m = rep.macro
        print(f"[run] {label:<24} {time.time()-t0:5.1f}s  "
              f"r@5={m['recall@5']:.3f} r@10={m['recall@10']:.3f} "
              f"mrr={m['mrr']:.3f} ndcg@5={m['ndcg@5']:.3f}", flush=True)

    # --- reconciliation: C vs D-reference on the SAME scorer + corpus ---
    # naive baseline is label-less -> scored under the agreed honest secondary
    # (match_mode='page', exact pdf page == gold page); structured runs use 'auto'.
    run("naive_baseline", make_baseline_fn(r, "vector"), match_mode="page")
    run("D_ref_hybrid", refret.make_retriever("refD_structured_hybrid"), persist=False)
    run("C_hybrid", make_retrieve_fn(r, use_lexical=True, use_vector=True,
                                     use_type=True, use_label=True, use_graph=False))
    # --- retrieval depth ---
    run("C_hybrid+graph_gated", make_retrieve_fn(r, use_lexical=True, use_vector=True,
                                                 use_type=True, use_label=True,
                                                 use_graph=True, gate_graph=True))
    run("C_hybrid+coarse_to_fine", make_retrieve_fn(r, use_lexical=True, use_vector=True,
                                                     use_type=True, use_label=True,
                                                     coarse_to_fine=True))
    run("C_hybrid+rerank", make_retrieve_fn(r, use_lexical=True, use_vector=True,
                                            use_type=True, use_label=True, rerank=True))
    run("C_full", make_retrieve_fn(r, use_lexical=True, use_vector=True, use_type=True,
                                   use_label=True, use_graph=True, gate_graph=True,
                                   coarse_to_fine=True, rerank=True))

    # --- THE ONE RECONCILED TABLE ---
    print("\n" + "=" * 100)
    print(f"RECONCILED BAKE-OFF — D's harness, match_mode={MATCH}, A's frozen corpus, 26 queries")
    print("=" * 100)
    cols = ["recall@5", "recall@10", "mrr", "ndcg@5", "exact_label_hit_rate", "traceability"]
    print(f"{'run':<24}" + "".join(f"{c.replace('_hit_rate','_hit'):>13}" for c in cols) + f"{'p50ms':>9}")
    for label in ["naive_baseline", "D_ref_hybrid", "C_hybrid", "C_hybrid+graph_gated",
                  "C_hybrid+coarse_to_fine", "C_hybrid+rerank", "C_full"]:
        rep, lat = reps[label]
        m = rep.macro
        lats = sorted(lat.values()); p50 = lats[len(lats) // 2] if lats else float("nan")
        print(f"{label:<24}" + "".join(f"{m.get(c, float('nan')):>13.3f}" for c in cols)
              + f"{p50:>9.0f}")

    # --- reconciliation delta C vs D ---
    cm, dm = reps["C_hybrid"][0].macro, reps["D_ref_hybrid"][0].macro
    print("\nRECONCILIATION  C_hybrid vs D_ref_hybrid (same scorer, same corpus):")
    for c in ["recall@5", "recall@10", "mrr", "ndcg@5"]:
        print(f"  {c:<12} C={cm[c]:.3f}  D={dm[c]:.3f}  Δ(C−D)={cm[c]-dm[c]:+.3f}")

    # --- depth deltas vs C_hybrid ---
    base = reps["C_hybrid"][0].macro
    print("\nRETRIEVAL-DEPTH Δ vs C_hybrid:")
    for label in ["C_hybrid+graph_gated", "C_hybrid+coarse_to_fine", "C_hybrid+rerank", "C_full"]:
        m = reps[label][0].macro
        print(f"  {label:<24} Δr@5={m['recall@5']-base['recall@5']:+.3f}  "
              f"Δr@10={m['recall@10']-base['recall@10']:+.3f}  "
              f"Δmrr={m['mrr']-base['mrr']:+.3f}  Δndcg@5={m['ndcg@5']-base['ndcg@5']:+.3f}")

    # --- per-category: did intent-gated graph lift structural? ---
    print("\nBY CATEGORY recall@5 | mrr  (C_hybrid vs +graph_gated vs C_full):")
    for cat in ["direct", "conceptual", "structural", "graph_expansion"]:
        a = reps["C_hybrid"][0].by_category.get(cat, {})
        b = reps["C_hybrid+graph_gated"][0].by_category.get(cat, {})
        d = reps["C_full"][0].by_category.get(cat, {})
        print(f"  {cat:<16} hybrid {a.get('recall@5',float('nan')):.2f}/{a.get('mrr',float('nan')):.2f}   "
              f"+graph {b.get('recall@5',float('nan')):.2f}/{b.get('mrr',float('nan')):.2f}   "
              f"full {d.get('recall@5',float('nan')):.2f}/{d.get('mrr',float('nan')):.2f}")

    # --- rerank latency (the R3 constraint) ---
    print("\nSPEED / COST")
    print(f"  query embeddings: {r.embed_calls} calls, {1000*r.embed_seconds/max(r.embed_calls,1):.0f} ms/call (cached)")
    rl = sorted(reps["C_hybrid+rerank"][1].values())
    print(f"  C_hybrid+rerank per-query latency: p50={rl[len(rl)//2]:.0f}ms "
          f"mean={sum(rl)/len(rl):.0f}ms (R2 was ~3855ms p50)")
    rc = getattr(r, "rerank_cost", None)
    if rc:
        cost = rc['in']*1.0/1e6 + rc['out']*5.0/1e6
        print(f"  rerank (claude-haiku-4-5, pool=12, 180-char snippets, max_tokens=128): "
              f"{rc['calls']} calls, {rc['in']}in+{rc['out']}out tok, "
              f"~${cost:.4f} total (~${cost/max(rc['calls'],1):.5f}/query)")
    r.close()


if __name__ == "__main__":
    main()

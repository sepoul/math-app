"""Track C — page-aware scoring for the LABEL-LESS naive baseline.

Track D's harness matches a retrieved item to gold on `node_id` or `label`. The
naive baseline (fixed windows) has NEITHER, so it scores 0.000 on every metric —
which makes the head-to-head "structured wins infinitely", not an honest gap.

D anticipated this and shipped a **pdf page** on every gold item (the
GOLD_CONTRACT ask from R1). This module scores the baseline on that page stick
using D's OWN metric *definitions* (recall@k / MRR / nDCG via metrics.py) — only
the match predicate changes: a baseline window "hits" a gold item if the window's
`page_pdf_start` is within ±tol pages of the gold item's pdf page. This is NOT a
new metric — it's the same recall/MRR/nDCG, made applicable to a system that can
only be located by page. We apply the SAME page predicate to the structured
system too, so the page-based column is a like-for-like comparison.

Run after run_eval.py (CWD = spikes/book-rag):
    .venv/bin/python track-c/score_baseline_pages.py
"""
from __future__ import annotations

import sys
import math
import pathlib
import importlib.util

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # spikes/book-rag, so `_shared` resolves


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, HERE / fn)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m
    spec.loader.exec_module(m); return m


metrics = _load("metrics", "_vendor_metrics.py")
harness = _load("harness", "_vendor_harness.py")
from retrieve_r2 import Retriever, make_baseline_fn, make_retrieve_fn  # noqa: E402

PAGE_TOL = 1  # a window on the gold page ±1 counts as locating the material


def load_gold_pages():
    """query_id -> [(gold_pdf_page, relevance)]. The pdf page lives in D's gold
    file-mirror (`page_pdf`), not the d_gold table column, so read the JSON."""
    import json
    gj = json.loads((HERE / "_vendor_gold.json").read_text())["gold"]
    return {qid: [(int(it["page_pdf"]), int(it.get("relevance", 1)))
                  for it in items if it.get("page_pdf") is not None]
            for qid, items in gj.items()}


def page_recall_mrr_ndcg(pages: list[int], gold: list[tuple[int, int]], k: int):
    """recall@k / MRR / nDCG@k using a page-proximity match (±PAGE_TOL)."""
    rel = [(p, r) for p, r in gold if r > 0]
    if not rel:
        return float("nan"), 0.0, float("nan")

    def hit(retrieved_page, gold_page):
        return retrieved_page is not None and abs(retrieved_page - gold_page) <= PAGE_TOL

    topk = pages[:k]
    found = sum(1 for gp, _ in rel if any(hit(rp, gp) for rp in topk))
    recall = found / len(rel)
    rr = 0.0
    for i, rp in enumerate(pages):
        if any(hit(rp, gp) for gp, _ in rel):
            rr = 1.0 / (i + 1); break

    def gain(rp):
        best = 0
        for gp, g in rel:
            if hit(rp, gp):
                best = max(best, g)
        return best
    dcg = sum((2 ** gain(rp) - 1) / math.log2(i + 2) for i, rp in enumerate(topk))
    ideal = sorted((g for _, g in rel), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    ndcg = dcg / idcg if idcg else 0.0
    return recall, rr, ndcg


def score_pages(retrieve_fn, queries, gold_pages, k=10):
    rec, mrr, ndcg = [], [], []
    for qid, q in queries.items():
        cands = retrieve_fn(q["query_text"], k) or []
        pages = [c.get("page_pdf_start") for c in cands]
        r, rr, n = page_recall_mrr_ndcg(pages, gold_pages.get(qid, []), 5)
        if r == r:
            rec.append(r); ndcg.append(n)
        mrr.append(rr)
    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    return mean(rec), mean(mrr), mean(ndcg)


def main():
    queries = harness.load_queries(HERE / "_vendor_queries.json")
    gold_pages = load_gold_pages()
    r = Retriever()

    print(f"PAGE-AWARE scoring (±{PAGE_TOL} pdf page; D's gold pages; recall@5/MRR/nDCG@5)")
    print("-" * 70)
    systems = [
        ("naive_baseline (vec)", make_baseline_fn(r, "vector")),
        ("naive_baseline (lex)", make_baseline_fn(r, "lexical")),
        ("structured hybrid_full", make_retrieve_fn(r, use_lexical=True, use_vector=True,
                                                    use_type=True, use_label=True)),
        ("structured +rerank", make_retrieve_fn(r, use_lexical=True, use_vector=True,
                                                use_type=True, use_label=True,
                                                use_graph=True, rerank=True)),
    ]
    print(f"{'system':<26}{'recall@5':>10}{'mrr':>8}{'ndcg@5':>8}")
    for name, fn in systems:
        rec, mrr, ndcg = score_pages(fn, queries, gold_pages)
        print(f"{name:<26}{rec:>10.3f}{mrr:>8.3f}{ndcg:>8.3f}")
    r.close()


if __name__ == "__main__":
    main()

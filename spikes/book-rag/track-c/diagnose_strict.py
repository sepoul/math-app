"""Track C — R4 diagnostic: locate the strict-recall ceiling misses.

strict recall@5 (~0.66) < page-aware (~0.85): some queries find the right PAGE but
not the right exact UNIT in top-5. This prints, per query, the gold primary unit,
whether it was a STRICT hit (node_id/label) and/or a PAGE hit in top-5, and the
top-5 C_full results — so we can see exactly which units are being out-ranked and
why (the `weak_vector` misses the coordinator flagged).

Usage (CWD = spikes/book-rag): .venv/bin/python track-c/diagnose_strict.py [--config NAME]
"""
from __future__ import annotations

import sys
import pathlib
import importlib.util

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))


def _load(n, f):
    s = importlib.util.spec_from_file_location(n, HERE / f)
    m = importlib.util.module_from_spec(s); sys.modules[n] = m; s.loader.exec_module(m); return m


metrics = _load("metrics", "_vendor_metrics.py")
harness = _load("harness", "_vendor_harness.py")
from retrieve_r2 import Retriever, C_FULL_CFG  # noqa: E402


def norm(s):
    return " ".join((s or "").lower().split())


def main():
    queries = harness.load_queries(HERE / "_vendor_queries.json")
    gold = harness.load_gold(HERE / "_vendor_gold.json")
    r = Retriever()
    n_strict5 = n_page5 = n_weak = 0
    weak_cases = []
    for qid, q in queries.items():
        cands = [c.as_dict() for c in r.hybrid(q["query_text"], k=10, **C_FULL_CFG)]
        top5 = cands[:5]
        prim = [g for g in gold[qid] if g.relevance == 2]  # primary gold
        if not prim:
            continue
        # strict hit: any top5 matches a primary by node_id or label
        def strict_hit():
            for g in prim:
                for c in top5:
                    if (c.get("node_id") and g.gold_node_id and c["node_id"] == g.gold_node_id) \
                       or (norm(c.get("label")) and norm(c.get("label")) == norm(g.gold_label)):
                        return True
            return False
        def page_hit():
            for g in prim:
                if g.page_pdf is None:
                    continue
                for c in top5:
                    if c.get("page_pdf_start") == g.page_pdf:
                        return True
            return False
        s, p = strict_hit(), page_hit()
        n_strict5 += s; n_page5 += p
        if p and not s:  # weak_vector: page found, exact unit missed in top5
            n_weak += 1
            weak_cases.append((qid, q["category"], q["query_text"], prim, top5))

    n = sum(1 for qid in queries if any(g.relevance == 2 for g in gold[qid]))
    print(f"primary-gold queries: {n}")
    print(f"strict hit@5: {n_strict5}/{n} = {n_strict5/n:.3f}")
    print(f"page   hit@5: {n_page5}/{n} = {n_page5/n:.3f}")
    print(f"WEAK_VECTOR (page hit, strict miss) @5: {n_weak}\n")
    for qid, cat, qt, prim, top5 in weak_cases:
        print("=" * 78)
        print(f"{qid} [{cat}]  {qt}")
        print("  GOLD primary:", [(g.gold_label, g.gold_node_id, g.page_pdf) for g in prim])
        for i, c in enumerate(top5, 1):
            print(f"   {i}. {str(c.get('label')):28} p{c.get('page_pdf_start')} "
                  f"node={c.get('node_id')} score={c.get('score')}")
    r.close()


if __name__ == "__main__":
    main()

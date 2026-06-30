"""Track D — self-test of the measuring stick (no DB, no real retriever).

Proves the metrics + harness work end-to-end by scoring two MOCK retrievers
against the real gold:
  * oracle   — returns each query's gold (primary first), fully traceable.
  * degraded — drops half the gold, mis-orders, and omits page/heading on some
               results (to show traceability < 1 and recall < 1).

Run: /abs/.venv/bin/python track-d/selftest.py   (CWD = spikes/book-rag)
This is the contract demo Track C reads to learn how to wire its retriever.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harness import evaluate, load_gold, load_queries  # noqa: E402

QUERIES = load_queries()
GOLD = load_gold()

# heading paths so mock results are "traceable" (page + heading_path present)
_HP = ["Chapter 2: Manifolds", "§7 Quotients", "7.x"]


def oracle(query_text: str, k: int):
    """Perfect retriever: find the query, emit its gold as ranked candidates."""
    qid = next((qid for qid, q in QUERIES.items() if q["query_text"] == query_text), None)
    if qid is None:
        return []
    items = sorted(GOLD[qid], key=lambda g: -g.relevance)
    return [{"label": g.gold_label, "score": float(g.relevance),
             "page_pdf_start": 94, "heading_path": _HP,
             "signals": {"mock": "oracle"}} for g in items][:k]


def degraded(query_text: str, k: int):
    """Imperfect retriever: keep only the lowest-relevance half, reversed order,
    and strip traceability from every other result."""
    qid = next((qid for qid, q in QUERIES.items() if q["query_text"] == query_text), None)
    if qid is None:
        return []
    items = sorted(GOLD[qid], key=lambda g: g.relevance)  # WORST first (bad order)
    half = items[: max(1, len(items) // 2)]
    out = []
    for i, g in enumerate(half):
        traceable = i % 2 == 0
        out.append({"label": g.gold_label, "score": 1.0 / (i + 1),
                    "page_pdf_start": 94 if traceable else None,
                    "heading_path": _HP if traceable else None,
                    "signals": {"mock": "degraded"}})
    return out[:k]


def main() -> None:
    for name, fn in [("oracle", oracle), ("degraded", degraded)]:
        report, _, lat = evaluate(fn, run_label=f"selftest_{name}", persist=False)
        print("=" * 60)
        print(report.summary_table())
        print(f"mean latency: {sum(lat.values())/len(lat):.3f} ms (mock)")
        print()
    # sanity assertions
    rep_o, _, _ = evaluate(oracle, "selftest_oracle", persist=False)
    assert rep_o.macro["recall@10"] > 0.99, rep_o.macro
    assert rep_o.macro["mrr"] > 0.99, rep_o.macro
    assert rep_o.macro["traceability"] > 0.99, rep_o.macro
    rep_d, _, _ = evaluate(degraded, "selftest_degraded", persist=False)
    assert rep_d.macro["recall@10"] < rep_o.macro["recall@10"], "degraded should recall less"
    assert rep_d.macro["traceability"] < 1.0, "degraded should be partly untraceable"
    print("ASSERTIONS PASSED: oracle≈perfect, degraded strictly worse.")


if __name__ == "__main__":
    main()

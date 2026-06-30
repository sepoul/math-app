"""Track D R3 — the ONE agreed bake-off (reconciled with Track C).

THE RECONCILE (resolved): R2 reported refD recall@5=0.816 while C reported its
hybrid at 0.583. Scoring BOTH through this one harness with one explicit rule
showed the gap was **matching strictness, not retriever quality**:
  * 0.816 = page-overlap fallback applied to a structured retriever (too generous
            — credits any chunk on the gold's page, not the right unit).
  * 0.583 = strict node_id/label match (the right *unit*), which is what a
            structured-RAG verdict should measure.

AGREED RULE (applied identically to everything here):
  * label-bearing retrievers (all structured + ablations) -> match_mode='strict'
    i.e. exact a_nodes node_id OR exact label. (Label is the freeze-stable key:
    A's R3 freeze renumbered node_id suffixes — theorem117->theorem123 — but
    labels are stable and C's d_results were keyed to the pre-freeze ids, so we
    join on label and the score is invariant to the renumber.)
  * the naive baseline carries NO label/node_id -> match_mode='page' (its only
    fair rule; it can only be credited by landing on the gold's page).
  * gold = all relevance>=1 (graded); nDCG uses the grades.

VERDICT FIGURE WE CITE: Track C's **+rerank**, strict — recall@5=0.656,
MRR=0.738, nDCG@5=0.639, exact-label-hit=0.577, traceability=1.000. It is the
best structured config and beats the reference yardstick (refD 0.554 strict);
C's elaborate hybrid + rerank is justified (it is NOT a case of simplicity
winning). The structure-vs-naive direction is unambiguous on the one rule the
baseline can be scored under (page): +rerank 0.869 vs naive 0.718 recall@5, and
+0.357 MRR / +0.577 exact-label / +1.000 traceability.
"""
from __future__ import annotations

import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from harness import load_gold, load_queries, category_map      # noqa: E402
from metrics import RetrievedItem, score_run                    # noqa: E402
from _shared.db import connect, SCHEMA                           # noqa: E402

# (run_label, match_mode, kind) — the agreed slate.
STRUCTURED = ["+rerank", "hybrid_full", "+graph_expansion", "+type_boost",
              "lex_vec", "vector_only", "refD_structured_hybrid"]
BASELINES = ["naive_baseline"]
COLS = ["recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@5",
        "exact_label_hit_rate", "traceability"]


def load_run(rl):
    by_q = collections.defaultdict(list)
    with connect() as c, c.cursor() as cur:
        cur.execute(f"""select query_id, rank, retrieved_node_id, retrieved_chunk_id, score, signals
                        from {SCHEMA}.d_results where run_label=%s order by query_id, rank;""", (rl,))
        for qid, rk, nid, cid, sc, sig in cur.fetchall():
            sig = sig or {}
            by_q[qid].append(RetrievedItem(
                query_id=qid, rank=rk, retrieved_node_id=nid, retrieved_chunk_id=cid,
                score=sc, label=sig.get("label"), page_pdf_start=sig.get("page_pdf_start"),
                heading_path=sig.get("heading_path"), signals=sig))
    return by_q


def main(persist: bool = True):
    gold = load_gold(); q = load_queries(); cm = category_map(q)
    present = _present_runs()
    rows = []
    for rl in STRUCTURED:
        if rl not in present:
            continue
        rep = score_run(rl, load_run(rl), gold, cm, match_mode="strict")
        rows.append((rl, "strict", rep))
    for rl in BASELINES:
        if rl not in present:
            continue
        rep = score_run(rl, load_run(rl), gold, cm, match_mode="page")
        rows.append((rl, "page", rep))

    print("=" * 96)
    print("THE ONE AGREED BAKE-OFF  (structured=strict node/label · baseline=page-overlap)")
    print("=" * 96)
    print(f"{'run_label':<24}{'mode':<8}" + "".join(f"{c.replace('_',''):>13}"[:13] for c in COLS))
    for rl, mode, rep in rows:
        m = rep.macro
        tag = "  <-- CITE" if rl == "+rerank" else ""
        print(f"{rl:<24}{mode:<8}" + "".join(f"{m.get(c, float('nan')):>13.3f}" for c in COLS) + tag)

    print("\nAPPLES-TO-APPLES (structured ALSO scored page-overlap, vs the label-less baseline):")
    for rl in ["+rerank", "hybrid_full", "naive_baseline"]:
        if rl not in present:
            continue
        m = score_run(rl, load_run(rl), gold, cm, match_mode="page").macro
        print(f"  {rl:<16} page: recall@5={m['recall@5']:.3f} mrr={m['mrr']:.3f} "
              f"ndcg@5={m['ndcg@5']:.3f} exact-label={m['exact_label_hit_rate']:.3f} "
              f"trace={m['traceability']:.3f}")

    if persist:
        _persist_quality(rows)
    return rows


def _present_runs():
    with connect() as c, c.cursor() as cur:
        cur.execute(f"select distinct run_label from {SCHEMA}.d_results;")
        return {r[0] for r in cur.fetchall()}


def _persist_quality(rows):
    """Stamp the agreed scores into d_speed_cost (stage='quality', metric prefixed
    'agreed_') so the bake-off numbers are self-contained in the ledger."""
    import json
    with connect() as conn, conn.cursor() as cur:
        for rl, mode, rep in rows:
            cur.execute(f"delete from {SCHEMA}.d_speed_cost where run_label=%s and stage='quality_agreed';", (rl,))
            for metric, val in rep.macro.items():
                if val != val:  # NaN
                    continue
                cur.execute(
                    f"""insert into {SCHEMA}.d_speed_cost (stage, run_label, metric, value, detail)
                        values ('quality_agreed', %s, %s, %s, %s)""",
                    (rl, metric, float(val), json.dumps({"match_mode": mode, "gold": "rel>=1 graded"})))
        conn.commit()
    print("\npersisted agreed quality scores to d_speed_cost (stage='quality_agreed').")


if __name__ == "__main__":
    main(persist="--no-persist" not in sys.argv)

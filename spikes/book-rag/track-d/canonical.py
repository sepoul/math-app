"""Track D R4 — THE CANONICAL NUMBER (the figure the spike is cited by).

Scores Track C's SINGLE locked config `C_full` ONCE, through the agreed harness,
from ONE gold source, and reports the two honest columns side by side:

  STRICT     — match on exact a_nodes node_id OR exact label = "did we retrieve
               the RIGHT UNIT" (the structured-RAG claim).
  PAGE-AWARE — also credit a result on the gold's source page = "did we land in
               the RIGHT PLACE" (what an end user actually reads).

plus the naive_baseline row (PAGE-AWARE only — it carries no label/node_id, so
page-overlap is its sole fair rule). This RESOLVES the R3 presentation gap
(D reported strict 0.66, C reported page 0.85) as one config seen two ways — NOT
a disagreement. The page-aware column reproduces C's self-reported recall@5=0.854
to the digit; the strict column is the right-unit figure.

Match-rule notes:
  * Label is the freeze-stable join key. A's R3 freeze renumbered node_id
    suffixes (theorem117->theorem123); C_full's d_results carry the pre-freeze
    ids while gold carries post-freeze ids, so strict joins on LABEL and is
    invariant to the renumber (gold↔C_full node_id overlap is only 20/37).
  * One gold source: file-gold == db-gold (verified; the R3 load_gold_from_db
    page_pdf bug is fixed, so both compute identical strict AND page numbers).
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from harness import load_gold, load_gold_from_db, load_queries, category_map  # noqa: E402
from metrics import RetrievedItem, score_run                                  # noqa: E402
from _shared.db import connect, SCHEMA                                         # noqa: E402

CANONICAL_RUN = "C_full"          # C's single locked config on corpus track-a-r1
BASELINE_RUN = "naive_baseline"


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


def _verify_one_gold_source():
    """The figure must come from one gold source — confirm file==db gold."""
    fg, dg = load_gold(), load_gold_from_db()
    def sig(items):
        return sorted((x.gold_label, x.relevance, x.page_pdf, x.gold_node_id) for x in items)
    mismatch = [q for q in fg if sig(fg[q]) != sig(dg.get(q, []))]
    fp = sum(1 for v in fg.values() for x in v if x.page_pdf is not None)
    dp = sum(1 for v in dg.values() for x in v if x.page_pdf is not None)
    print(f"gold source check: file page_pdf {fp}/66, db page_pdf {dp}/66, "
          f"file==db: {'YES' if not mismatch else 'NO ' + str(mismatch)}")
    return not mismatch


def main(persist: bool = True):
    _verify_one_gold_source()
    gold = load_gold(); q = load_queries(); cm = category_map(q)

    cf = load_run(CANONICAL_RUN)
    cf_strict = score_run(CANONICAL_RUN, cf, gold, cm, match_mode="strict").macro
    cf_page = score_run(CANONICAL_RUN, cf, gold, cm, match_mode="page").macro
    nb_page = score_run(BASELINE_RUN, load_run(BASELINE_RUN), gold, cm, match_mode="page").macro

    # latency for C_full (C logged it into d_speed_cost)
    lat = {}
    with connect() as c, c.cursor() as cur:
        cur.execute(f"""select metric, value from {SCHEMA}.d_speed_cost
                        where run_label=%s and metric like 'query_latency%%';""", (CANONICAL_RUN,))
        lat = {m: v for m, v in cur.fetchall()}

    print("\n" + "=" * 84)
    print(f"THE CANONICAL BAKE-OFF — {CANONICAL_RUN} (C's locked config, corpus track-a-r1)")
    print("=" * 84)
    hdr = f"{'metric':<24}{'STRICT(unit)':>15}{'PAGE(place)':>15}{'naive(page)':>15}"
    print(hdr)
    for label, key in [("recall@5", "recall@5"), ("recall@10", "recall@10"),
                       ("MRR", "mrr"), ("nDCG@5", "ndcg@5"),
                       ("exact-label-hit", "exact_label_hit_rate"),
                       ("traceability", "traceability")]:
        print(f"{label:<24}{cf_strict[key]:>15.3f}{cf_page[key]:>15.3f}{nb_page.get(key, float('nan')):>15.3f}")
    p50 = lat.get("query_latency_p50_ms", float("nan"))
    p95 = lat.get("query_latency_p95_ms", float("nan"))
    print(f"{'latency p50 / p95 (ms)':<24}{p50:>7.0f} /{p95:>6.0f}{'':>15}{'(see ledger)':>15}")
    print("\nThe bracket: structured RAG recovers the RIGHT UNIT for "
          f"{cf_strict['recall@5']*100:.0f}% of queries@5 (strict) and the RIGHT PLACE for "
          f"{cf_page['recall@5']*100:.0f}% (page). Naive baseline: {nb_page['recall@5']*100:.0f}% "
          "right-place, 0% right-unit (no label/traceability).")

    if persist:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(f"delete from {SCHEMA}.d_speed_cost where stage='canonical';")
            for mode, macro in [("strict", cf_strict), ("page", cf_page)]:
                for metric, val in macro.items():
                    if val != val:
                        continue
                    cur.execute(
                        f"""insert into {SCHEMA}.d_speed_cost (stage, run_label, metric, value, detail)
                            values ('canonical', %s, %s, %s, %s)""",
                        (CANONICAL_RUN, metric, float(val),
                         json.dumps({"match_mode": mode, "gold": "rel>=1 graded", "corpus": "track-a-r1"})))
            conn.commit()
        print("\npersisted canonical scores to d_speed_cost (stage='canonical').")
    return cf_strict, cf_page, nb_page


if __name__ == "__main__":
    main(persist="--no-persist" not in sys.argv)

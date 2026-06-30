"""Track B R4 — the semantic-edge experiment: depends_on LIFT vs NOISE.

A/B-compares bounded expansion WITHOUT depends_on (R3 deterministic tier) vs WITH
depends_on (the §11 semantic tier) across all 5 of D's structural/expansion gold
queries. Reports, per query:
  - gold recall before / after (the LIFT)
  - extra neighbors depends_on introduced, split gold-hit vs non-gold (the NOISE)
and globally: how many depends_on neighbors are spurious (non-gold) vs useful.

Seeds + gold resolved live from the DB (A's IDs churn; D re-syncs).

Run AFTER graph_build.py + semantic_edges.py:
    .venv/bin/python track-b/depends_on_experiment.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from _shared.db import connect  # noqa: E402
from expand import expand, _load_adjacency, resolve_seed  # noqa: E402

# query_id -> (seed-kind, seed-key) ; intent is always the expansion family here
SEED_SPECS = {
    "D-017": ("label", "Theorem 7.7"),   # structural_neighbor (control: no expansion need)
    "D-020": ("id", "book.sub7.6"),       # structural_contains (control)
    "D-022": ("id", "book.sec3"),         # structural_contains (control)
    "D-023": ("label", "Theorem 7.9"),    # expansion (target)
    "D-026": ("label", "Theorem 7.7"),    # expansion (target)
}


def run():
    adj = _load_adjacency(0.5)
    with connect() as c, c.cursor() as cur:
        print("DEPENDS_ON EXPERIMENT — bounded expansion, deterministic vs +semantic\n")
        tot_det_hit = tot_sem_hit = tot_gold = 0
        global_extra_gold = global_extra_noise = 0
        for qid, (skind, skey) in SEED_SPECS.items():
            seed = resolve_seed(cur, skind, skey)
            cur.execute("select gold_node_id from d_gold where query_id=%s;", (qid,))
            gold = {r[0] for r in cur.fetchall()}
            if not seed or not gold:
                print(f"{qid}: unresolved (seed={seed}, gold={len(gold)})\n")
                continue

            det = expand(seed, intent="expansion_deterministic", _adj=adj)
            sem = expand(seed, intent="expansion", _adj=adj)  # adds depends_on
            det_nodes = {n.node_id for n in det} | {seed}
            sem_nodes = {n.node_id for n in sem} | {seed}

            det_hit = gold & det_nodes
            sem_hit = gold & sem_nodes
            # DISTINCT nodes that only appear once depends_on is on (no path double-count):
            extra = sem_nodes - det_nodes
            extra_gold = extra & gold
            extra_noise = extra - gold

            tot_det_hit += len(det_hit); tot_sem_hit += len(sem_hit); tot_gold += len(gold)
            global_extra_gold += len(extra_gold); global_extra_noise += len(extra_noise)

            print(f"=== {qid}  seed={seed} ({skey})")
            print(f"    gold={len(gold)}  det-recall={len(det_hit)}/{len(gold)}="
                  f"{len(det_hit)/len(gold):.0%}  -> +depends_on={len(sem_hit)}/{len(gold)}="
                  f"{len(sem_hit)/len(gold):.0%}   LIFT={len(sem_hit)-len(det_hit)}")
            print(f"    depends_on added {len(extra)} distinct new node(s): "
                  f"{len(extra_gold)} gold-hit, {len(extra_noise)} non-gold")
            for n in sem:
                if n.via_edge in ("depends_on", "depended_on_by"):
                    tag = "GOLD" if n.node_id in gold else "noise"
                    print(f"      {n.via_edge}-> {n.node_id}  d{n.depth} s={n.score}  [{tag}]")
            print()

        print("================ TOTALS ================")
        print(f"gold recall: deterministic {tot_det_hit}/{tot_gold} = {tot_det_hit/tot_gold:.1%}"
              f"  ->  +depends_on {tot_sem_hit}/{tot_gold} = {tot_sem_hit/tot_gold:.1%}")
        print(f"LIFT: +{tot_sem_hit - tot_det_hit} gold nodes recovered "
              f"({(tot_sem_hit-tot_det_hit)/tot_gold:+.1%})")
        print(f"NOISE: depends_on introduced {global_extra_noise} non-gold neighbor(s) "
              f"across all 5 queries")
        # global: total depends_on edges and how many are reachable from any seed
        cur2 = connect().cursor()
        cur2.execute("select count(*) from b_node_edges where edge_type='depends_on';")
        print(f"depends_on edges in graph: {cur2.fetchone()[0]} (all proof-cited, conf 0.9)")


if __name__ == "__main__":
    run()

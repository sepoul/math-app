"""Track B R4 — conservative, evidence-backed `depends_on` semantic edges (§11).

The R4 experiment: do optional semantic edges earn their place in #50? R3 showed
deterministic edges cap graph-expansion recall at 60-75%; the misses are
cross-subsection dependencies. This module derives `depends_on` ONLY from
defensible textual signals, scores each with evidence, and lets us measure
recall LIFT vs NOISE.

SIGNALS (defensible only — a false bridge is worse than a miss, per #53):
  1. PROOF-CITED  (conf 0.9): node N's proof text cites labeled result X
     ("Apply Corollary 7.10", "By Theorem 7.7") -> N depends_on X. Strong: the
     author explicitly invokes X to establish N.
  2. STATEMENT-CITED (conf 0.8): N's own statement says "by/using/apply <Label>".
     (0 in this slice — Tu keeps dependency language in proofs — kept for
     generality.)

NOT derived: term-overlap / topical adjacency / same-section co-membership.
Those are speculative; they would inject the exact global-neighbor noise that
hurt C in R2. We prefer a miss to a false edge.

Writes to b_node_edges (edge_type='depends_on'), additive on top of the
deterministic tier. Run AFTER graph_build.py.

    .venv/bin/python track-b/semantic_edges.py            # derive + persist + report
    .venv/bin/python track-b/semantic_edges.py --dry-run  # derive + report only
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from _shared.db import connect  # noqa: E402

THM_LIKE = {"theorem", "proposition", "lemma", "corollary"}
ENV_KINDS = "Theorem|Proposition|Lemma|Corollary|Definition"
LABEL_PAT = re.compile(rf"\b({ENV_KINDS})\s+(\d+(?:\.\d+)*)")
BY_PAT = re.compile(
    rf"\b(?:by|using|from|apply|applying|via)\s+({ENV_KINDS})\s+(\d+(?:\.\d+)*)",
    re.I)


def derive_depends_on() -> list[dict]:
    """Return evidence-backed depends_on edges: {from,to,edge_type,confidence,evidence}."""
    edges: list[dict] = []
    seen: set[tuple] = set()
    with connect() as c, c.cursor() as cur:
        cur.execute("select node_id, kind, label, "
                    "coalesce(text_normalized,text_raw,''), proves from a_nodes;")
        rows = cur.fetchall()
    lab2id = {lab.lower(): nid for nid, kind, lab, _, _ in rows
              if lab and kind in (THM_LIKE | {"definition"})}
    text = {nid: txt for nid, _, _, txt, _ in rows}

    def _emit(frm, to, et, conf, ev):
        k = (frm, to, et)
        if k in seen:                 # keep highest-confidence evidence per pair
            for e in edges:
                if (e["from_node_id"], e["to_node_id"], e["edge_type"]) == k and conf > e["confidence"]:
                    e["confidence"], e["evidence"] = conf, ev
            return
        seen.add(k)
        edges.append({"from_node_id": frm, "to_node_id": to,
                      "edge_type": et, "confidence": conf, "evidence": ev})

    def add(frm, to, conf, ev):
        # emit BOTH directions (mirrors references/referenced_by): `depends_on`
        # (dependent -> dependency) for "what does X rely on", and
        # `depended_on_by` (dependency -> dependent) for "what depends on X" —
        # which is what D-023's "results that depend on the construction" needs.
        if frm == to:
            return
        _emit(frm, to, "depends_on", conf, ev)
        _emit(to, frm, "depended_on_by", conf, ev + ["(reverse)"])

    # 1. PROOF-CITED: the proven node depends_on each labeled result its proof cites
    for nid, kind, lab, txt, proves in rows:
        if kind != "proof" or not proves:
            continue
        for m in LABEL_PAT.finditer(txt):
            tgt = lab2id.get(f"{m.group(1)} {m.group(2)}".lower())
            if tgt:
                add(proves, tgt, 0.9,
                    [f"proof of {proves} cites '{m.group(0)}'", "signal=proof_cited"])

    # 2. STATEMENT-CITED: thm-like node whose statement says "by/using <Label>"
    for nid, kind, lab, txt, proves in rows:
        if kind not in THM_LIKE:
            continue
        for m in BY_PAT.finditer(txt):
            tgt = lab2id.get(f"{m.group(1)} {m.group(2)}".lower())
            if tgt:
                add(nid, tgt, 0.8,
                    [f"statement of {nid} says '{m.group(0)}'", "signal=statement_cited"])
    return edges


def persist(edges: list[dict]):
    with connect() as c, c.cursor() as cur:
        cur.execute("delete from b_node_edges where edge_type in ('depends_on','depended_on_by');")
        for e in edges:
            cur.execute(
                "insert into b_node_edges (from_node_id,to_node_id,edge_type,confidence,evidence) "
                "values (%s,%s,%s,%s,%s)",
                (e["from_node_id"], e["to_node_id"], e["edge_type"], e["confidence"],
                 json.dumps(e["evidence"])))
        c.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    edges = derive_depends_on()
    by_signal: dict[str, int] = {}
    for e in edges:
        sig = next((x.split("=")[1] for x in e["evidence"] if x.startswith("signal=")), "?")
        by_signal[sig] = by_signal.get(sig, 0) + 1
    print(f"derived {len(edges)} depends_on edges  by signal: {by_signal}")
    for e in edges:
        print(f"  {e['from_node_id']} -> {e['to_node_id']}  conf={e['confidence']}  {e['evidence'][0]}")
    if not args.dry_run:
        persist(edges)
        print(f"\npersisted {len(edges)} depends_on edges to b_node_edges")


if __name__ == "__main__":
    main()

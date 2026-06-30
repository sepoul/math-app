"""Track D R2 — map gold STABLE LABELS -> Track A's real a_nodes.node_id.

R1 authored gold against stable Tu labels because a_nodes was empty. A's
canonical nodes are now live (run_id track-a-r1, 143 nodes, ids book.ch*/sec*/
sub*.<kind><n>). This resolves every gold_label to a node_id where one exists,
writes the resolved node_ids back into queries/gold.json (keeping gold_label +
page anchors so C's label-less naive baseline still scores on the same stick),
then reloads d_gold.

Resolution rules (built from A's actual scheme, inspected live):
  * Formal environments — gold_label == a_nodes.label verbatim
    ("Theorem 7.7", "Proposition 7.3", "Lemma 1.4", "Corollary 7.8",
     "Example 1.3", "Definition 7.5", ...).  -> exact label match.
  * Sections/subsections — gold_label "subsection N.M <title>" or "section N".
    A labels these by NUMBER only (label='7.5'), id book.subN.M / book.secN.
    -> parse the leading number, map to the id.
  * Proofs — A labels every proof 'Proof' and links via `proves`. gold_label
    "Proof of <X>" -> resolve <X> to its node_id, then the proof node whose
    proves == that id.
  * Exercise/Problem alias — Tu's end-of-section "Problems" block is labeled
    Exercise N.k by A. Inline starred exercises mid-section (e.g. Tu's
    "Exercise 7.11" in §7.6) are NOT separate nodes in A's R1 output -> these
    resolve to None and are recorded as an extraction-coverage gap (kept as
    page-anchored gold so traceability/recall still penalize a miss).

Unresolved labels keep gold_node_id=null (matcher falls back to label, and the
page anchor still drives source-traceability). Run with the lab venv, CWD at
spikes/book-rag.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import connect, SCHEMA  # noqa: E402

QDIR = pathlib.Path(__file__).resolve().parents[1] / "queries"


def load_a_nodes():
    by_label: dict[str, str] = {}
    proves_to_proof: dict[str, str] = {}
    all_ids: set[str] = set()
    with connect() as c, cur_ctx(c) as cur:
        cur.execute(f"select node_id, kind, label, proves from {SCHEMA}.a_nodes;")
        for nid, kind, label, proves in cur.fetchall():
            all_ids.add(nid)
            if kind == "proof" and proves:
                proves_to_proof[proves] = nid
            elif label:
                by_label.setdefault(label.strip(), nid)
    return by_label, proves_to_proof, all_ids


def cur_ctx(conn):
    return conn.cursor()


def resolve(label: str, by_label, proves_to_proof) -> str | None:
    label = label.strip()
    # 1. exact formal-environment label
    if label in by_label:
        return by_label[label]
    # 2. proof of X
    m = re.match(r"^Proof of (.+)$", label)
    if m:
        target = resolve(m.group(1), by_label, proves_to_proof)
        if target:
            return proves_to_proof.get(target)
        return None
    # 3. subsection N.M <title>  ->  book.subN.M
    m = re.match(r"^subsection\s+(\d+)\.(\d+)\b", label)
    if m:
        return f"book.sub{m.group(1)}.{m.group(2)}"
    # 4. section N <title> -> book.secN
    m = re.match(r"^section\s+(\d+)\b", label)
    if m:
        return f"book.sec{m.group(1)}"
    return None


def main(apply: bool = True) -> None:
    by_label, proves_to_proof, all_ids = load_a_nodes()
    gold_path = QDIR / "gold.json"
    data = json.loads(gold_path.read_text())
    gold = data["gold"]

    resolved = unresolved = 0
    misses: list[tuple[str, str]] = []
    for qid, items in gold.items():
        for it in items:
            lbl = it.get("gold_label")
            nid = resolve(lbl, by_label, proves_to_proof) if lbl else None
            if nid and nid in all_ids:
                it["gold_node_id"] = nid
                resolved += 1
            else:
                it["gold_node_id"] = None
                unresolved += 1
                misses.append((qid, lbl))

    print(f"resolved {resolved} / {resolved+unresolved} gold labels -> node_id")
    if misses:
        print("UNRESOLVED (kept as page-anchored label gold):")
        for qid, lbl in misses:
            print(f"  {qid}: {lbl!r}")

    if apply:
        data["meta"]["anchoring"] = (
            "gold_node_id now resolved to Track A's a_nodes (run track-a-r1) where a node "
            "exists; gold_label + page_pdf kept so C's label-less naive baseline scores on "
            "the same stick. Unresolved labels (inline exercises A merged into prose) keep "
            "gold_node_id=null and remain page-anchored.")
        gold_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {gold_path}")


if __name__ == "__main__":
    main(apply="--dry-run" not in sys.argv)

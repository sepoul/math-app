"""Track D R2 — §17 failure-attribution.

For each query where the headline run (refD_structured_hybrid) misses a PRIMARY
gold item or mis-ranks it out of the top-3, classify the dominant cause into the
spec-§17 buckets and emit a histogram. This is what drives the go/no-go: it tells
us whether failures are UPSTREAM (extraction/structure — A/B) or RETRIEVAL
(lexical/vector/metadata/rerank — C), since "for math books, segmentation and
structural accuracy usually matter more than swapping embedding models."

Classification is evidence-based, computed from the LIVE tables (not guessed):

  graph_expansion   query category == graph_expansion and a primary gold node was
                    missed → bounded-walk/edge coverage gap (B §10-11).
  theorem_proof_boundary
                    gold targets a 'proof' node (proves != null) that A produced
                    but retrieval missed it → proof unit not surfaced.
  chunking_granularity / heading_segmentation
                    gold targets a SUBSECTION (book.subN.M) but C has NO subsection
                    chunk level (only section+leaf) → the unit literally cannot be
                    returned. Structural retrieval limitation, upstream of ranking.
  extraction_coverage
                    gold label has NO node in a_nodes at all (e.g. inline
                    'Exercise 7.11' A merged into prose) → can't retrieve a node
                    that was never extracted (A §8).
  weak_lexical      direct/label query, the gold node EXISTS as a c_chunk with the
                    label, but it wasn't in the lexical candidate set / ranked low
                    → FTS miss on the label/symbols (C §13).
  weak_vector       conceptual query, gold node exists as a c_chunk, missed →
                    embedding/paraphrase miss (C §12-13).
  metadata_rerank   gold node was retrieved (in candidate pool / top-10) but ranked
                    below k=3 → fusion/boost/rerank ordering issue (C §13).
"""
from __future__ import annotations

import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harness import load_gold, load_queries          # noqa: E402
from metrics import _matches                          # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import connect, SCHEMA                # noqa: E402

HEADLINE = "refD_structured_hybrid"


def _live_facts():
    """Pull the facts the classifier needs from the live tables."""
    with connect() as c, c.cursor() as cur:
        cur.execute(f"select node_id, kind, label, proves from {SCHEMA}.a_nodes;")
        a_by_label, a_kind = {}, {}
        for nid, kind, label, proves in cur.fetchall():
            if label:
                a_by_label.setdefault(label.strip(), nid)
            a_kind[nid] = kind
        # C chunk coverage: which node_ids + labels are actually indexed.
        cur.execute(f"select node_id, label from {SCHEMA}.c_chunks;")
        c_node_ids, c_labels = set(), set()
        for nid, label in cur.fetchall():
            if nid:
                c_node_ids.add(nid)
            if label:
                c_labels.add(label)
    return a_by_label, a_kind, c_node_ids, c_labels


def _load_results(run_label):
    """query_id -> ranked list of dicts {rank,label,node_id,signals}."""
    out = collections.defaultdict(list)
    with connect() as c, c.cursor() as cur:
        cur.execute(f"""select query_id, rank, retrieved_node_id, retrieved_chunk_id, signals
                        from {SCHEMA}.d_results where run_label=%s order by query_id, rank;""",
                    (run_label,))
        for qid, rank, nid, cid, sig in cur.fetchall():
            sig = sig or {}
            out[qid].append({"rank": rank, "node_id": nid, "chunk_id": cid,
                             "label": sig.get("label"), "kind": sig.get("kind"),
                             "page": sig.get("page_pdf_start"), "signals": sig})
    return out


def _norm(s):
    return " ".join((s or "").lower().split())


def _gid(g):
    """A gold item's match key: node_id preferred, else normalized label."""
    return g.gold_node_id or _norm(g.gold_label)


def _rid_set(results, n):
    """node_ids + normalized labels present in the top-n results."""
    ids, labels = set(), set()
    for r in results[:n]:
        if r.get("node_id"):
            ids.add(r["node_id"])
        if r.get("label"):
            labels.add(_norm(r["label"]))
    return ids, labels


def classify(qid, category, gold, results, facts):
    """Return (status, bucket) for the query's PRIMARY gold."""
    a_by_label, a_kind, c_node_ids, c_labels = facts
    primary = [g for g in gold if g.relevance == 2] or gold
    ids10, labels10 = _rid_set(results, 10)
    ids3, labels3 = _rid_set(results, 3)

    def in_top(g, ids, labels):
        return (g.gold_node_id in ids) or (_norm(g.gold_label) in labels)

    if any(in_top(g, ids3, labels3) for g in primary):
        return ("ok", None)

    miss = next((g for g in primary if not in_top(g, ids3, labels3)), primary[0])
    lbl = (miss.gold_label or "").strip()
    nid = miss.gold_node_id
    retrieved10 = in_top(miss, ids10, labels10)

    # 1. node never extracted by A (no node_id, label absent from a_nodes)
    if nid is None and lbl not in a_by_label and not lbl.startswith(("subsection", "section")):
        return ("miss", "extraction_coverage")
    # 2. node extracted by A but NOT indexed by C -> indexing/chunking gap
    if nid and nid not in c_node_ids:
        return ("miss", "chunking_coverage")
    # 3. proof boundary: gold is a proof node, retrieval didn't surface it
    if nid and a_kind.get(nid) == "proof" and not retrieved10:
        return ("miss", "theorem_proof_boundary")
    # 4. retrieved in top-10 but not top-3 -> fusion/boost/rerank ordering
    if retrieved10:
        return ("misrank", "metadata_rerank")
    # 5. graph-expansion: dependency walk not surfaced (no graph expansion in retriever)
    if category == "graph_expansion":
        return ("miss", "graph_expansion")
    # 6. node IS indexed by C but absent from top-10 -> signal miss
    return ("miss", "weak_lexical" if category == "direct" else "weak_vector")


def main():
    queries = load_queries(); gold = load_gold(); facts = _live_facts()
    results = _load_results(HEADLINE)
    if not results:
        print(f"NO d_results for {HEADLINE} yet — run score_runs.py first.")
        return
    hist = collections.Counter()
    rows = []
    for qid, q in queries.items():
        status, bucket = classify(qid, q["category"], gold[qid], results.get(qid, []), facts)
        if status == "ok":
            hist["ok"] += 1
            continue
        hist[bucket] += 1
        rows.append((qid, q["category"], status, bucket, q["query_text"][:42]))

    print(f"=== §17 FAILURE ATTRIBUTION — {HEADLINE} (primary gold not in top-3) ===\n")
    print(f"{'query':<7}{'category':<16}{'status':<9}{'bucket':<24}query")
    for qid, cat, st, bk, txt in sorted(rows, key=lambda r: r[3]):
        print(f"{qid:<7}{cat:<16}{st:<9}{bk:<24}{txt}")
    nq = len(queries)
    print(f"\n=== HISTOGRAM (n={nq} queries; ok={hist['ok']}) ===")
    UPSTREAM = {"extraction_coverage", "chunking_coverage", "theorem_proof_boundary",
                "heading_segmentation", "graph_expansion"}
    up = sum(v for k, v in hist.items() if k in UPSTREAM)
    rt = sum(v for k, v in hist.items() if k not in UPSTREAM and k != "ok")
    for bucket, n in hist.most_common():
        if bucket == "ok":
            continue
        tag = "UPSTREAM(A/B)" if bucket in UPSTREAM else "RETRIEVAL(C)"
        print(f"  {bucket:<24} {n:>3}   [{tag}]")
    print(f"\n  UPSTREAM (A/B structure/extraction/graph): {up}")
    print(f"  RETRIEVAL (C lexical/vector/metadata/rerank): {rt}")
    print(f"  hits in top-3: {hist['ok']}")
    return hist, rows


if __name__ == "__main__":
    main()

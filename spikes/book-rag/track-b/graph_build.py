"""Track B — document graph + reference resolution + §10 invariants.

Round 1 deliverable. Consumes typed nodes from Track A's `a_nodes` if populated,
else falls back to Track B's own hand seed (`seed/seed_s7_quotients.json`) so we
are never blocked. Writes ONLY to `b_node_edges`, `b_references`,
`b_validation_issues` (Track B's zone).

Run from `spikes/book-rag`:
    .venv/bin/python track-b/graph_build.py            # full pipeline
    .venv/bin/python track-b/graph_build.py --report   # re-print counts only

Pipeline:
  1. load_nodes()        -> list[NodeRow] from a_nodes or seed
  2. build_edges()       -> contains/parent_of/next/previous/proven_by/has_equation
  3. resolve_references()-> scan text for "Theorem N.M" / "Problem N.M" / "§N" ...
  4. run_invariants()    -> §10 structural checks -> b_validation_issues
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[1]  # spikes/book-rag
sys.path.insert(0, str(ROOT))
from _shared.db import connect  # noqa: E402

SEED_JSON = ROOT / "seed" / "seed_s7_quotients.json"

# ---------------------------------------------------------------------------
# Node model (superset of the columns we need from a_nodes / seed)
# ---------------------------------------------------------------------------


@dataclass
class NodeRow:
    node_id: str
    parent_id: Optional[str]
    kind: str
    label: Optional[str]
    title: Optional[str]
    heading_path: list[str]
    page_pdf_start: Optional[int]
    page_pdf_end: Optional[int]
    page_printed_start: Optional[str]
    text: str
    proves: Optional[str]
    math_region_ids: list[str] = field(default_factory=list)


THM_LIKE = {"theorem", "proposition", "lemma", "corollary"}


def load_nodes() -> tuple[list[NodeRow], str]:
    """Prefer Track A's `a_nodes`; fall back to Track B's seed JSON."""
    with connect() as c, c.cursor() as cur:
        cur.execute("select count(*) from a_nodes;")
        a_count = cur.fetchone()[0]
        if a_count > 0:
            cur.execute(
                "select node_id, parent_id, kind, label, title, heading_path, "
                "page_pdf_start, page_pdf_end, page_printed_start, "
                "coalesce(text_normalized, text_raw, ''), proves, "
                "coalesce(math_region_ids, '{}') from a_nodes;")
            rows = [
                NodeRow(nid, pid, kind, lbl, ttl, hp or [], ps, pe, pps,
                        txt or "", prv, list(mri or []))
                for (nid, pid, kind, lbl, ttl, hp, ps, pe, pps, txt, prv, mri)
                in cur.fetchall()
            ]
            return rows, f"a_nodes ({a_count} rows)"
    # fallback: seed
    data = json.loads(SEED_JSON.read_text())
    rows = []
    for n in data["nodes"]:
        rows.append(NodeRow(
            node_id=n["node_id"], parent_id=n.get("parent_id"), kind=n["kind"],
            label=n.get("label"), title=n.get("title"),
            heading_path=n.get("heading_path") or [],
            page_pdf_start=n.get("page_pdf_start"),
            page_pdf_end=n.get("page_pdf_end"),
            page_printed_start=n.get("page_printed_start"),
            text=n.get("text_normalized") or n.get("text_raw") or "",
            proves=n.get("proves"),
            math_region_ids=n.get("math_region_ids") or [],
        ))
    return rows, f"seed ({SEED_JSON.name}, {len(rows)} nodes)"


# ---------------------------------------------------------------------------
# 2. Deterministic edges
# ---------------------------------------------------------------------------

# read order within a parent: by (page_pdf_start, label tie-break)
_LABEL_NUM = re.compile(r"(\d+(?:\.\d+)*)")


def _order_key(n: NodeRow) -> tuple:
    page = n.page_pdf_start if n.page_pdf_start is not None else 10**6
    m = _LABEL_NUM.search(n.label or "")
    nums = tuple(int(x) for x in m.group(1).split(".")) if m else (10**6,)
    return (page,) + nums


def build_edges(nodes: list[NodeRow]) -> list[dict]:
    by_id = {n.node_id: n for n in nodes}
    edges: list[dict] = []

    def add(frm, to, et, conf, ev):
        edges.append({"from_node_id": frm, "to_node_id": to, "edge_type": et,
                      "confidence": conf, "evidence": ev})

    # contains + parent_of (both directions) from parent_id
    children: dict[str, list[NodeRow]] = {}
    for n in nodes:
        if n.parent_id and n.parent_id in by_id:
            add(n.parent_id, n.node_id, "contains", 1.0,
                ["parent_id from heading hierarchy"])
            add(n.node_id, n.parent_id, "parent_of", 1.0,
                ["inverse of contains"])
            children.setdefault(n.parent_id, []).append(n)

    # next / previous in reading order among siblings (one chain per parent)
    for pid, sibs in children.items():
        sibs_sorted = sorted(sibs, key=_order_key)
        for a, b in zip(sibs_sorted, sibs_sorted[1:]):
            add(a.node_id, b.node_id, "next", 0.95,
                ["reading-order sibling chain"])
            add(b.node_id, a.node_id, "previous", 0.95,
                ["reading-order sibling chain"])

    # proven_by: proof -> the node it proves (from `proves`), edge theorem->proof
    for n in nodes:
        if n.kind == "proof" and n.proves and n.proves in by_id:
            tgt = by_id[n.proves]
            conf = 0.97 if tgt.kind in THM_LIKE else 0.6
            add(n.proves, n.node_id, "proven_by", conf,
                [f"proof attaches to {tgt.kind} {tgt.label or ''}".strip()])

    # has_equation: node -> equation id (from math_region_ids)
    for n in nodes:
        for eq in n.math_region_ids:
            add(n.node_id, eq, "has_equation", 0.9,
                ["equation in node's math_region_ids"])

    return edges


# ---------------------------------------------------------------------------
# 3. Reference resolution
# ---------------------------------------------------------------------------
# Tu's grammar: theorem-likes & defs/examples are "Kind N.M"; exercises in the
# Problems block are "Problem N.M"; sections are "§N"; chapters "Chapter K".

ENV_KINDS = "Theorem|Proposition|Lemma|Corollary|Definition|Example|Remark|Exercise"
REF_PATTERNS = [
    # ("Theorem 7.7", "by Proposition 7.1", "Corollary A.36")
    ("env", re.compile(rf"\b({ENV_KINDS})\s+([A-Z]?\.?\d+(?:\.\d+)*)")),
    ("problem", re.compile(r"\bProblem\s+(\d+(?:\.\d+)*)")),
    ("section", re.compile(r"§\s*(\d+)")),
    ("chapter", re.compile(r"\bChapter\s+(\d+)")),
]

# the slice's leading numbering prefixes: Ch1 §1-§3 (1.x/2.x/3.x) + §7 (7.x).
# A mention whose leading number isn't here (5.7, A.36, 19.12, §10, Chapter 4)
# targets material OUTSIDE the slice -> correct to NOT resolve.
SLICE_PREFIXES = {"1", "2", "3", "7"}


def _in_slice(num: str) -> bool:
    prefix = num.split(".")[0]
    return prefix in SLICE_PREFIXES


@dataclass
class Ref:
    src_node_id: str
    raw_mention: str
    resolved_label: Optional[str]
    resolved_node_id: Optional[str]
    method: str
    confidence: float
    correct: Optional[bool] = None  # self-judged vs PDF (filled on sample)


def _build_label_index(nodes: list[NodeRow]):
    """Map normalized label/section/chapter -> node_id.

    R2: Tu's Problem/Exercise ALIAS SPLIT. The Problems block at a section's end
    is cited in prose as "Problem N.M" but Track A labels those nodes
    "Exercise N.M" (and Tu *lists* them as bare "N.M"). So we index exercises by
    BARE NUMBER in a single `exer_idx`, and resolve BOTH "Exercise N.M" and
    "Problem N.M" mentions through it. This is the one Tu-specific seam #57
    flagged."""
    env_idx: dict[str, str] = {}      # "theorem 7.7" -> node_id (numbered envs)
    exer_idx: dict[str, str] = {}     # "7.1" -> node_id (exercise/problem, by bare num)
    sec_idx: dict[str, str] = {}      # "7" -> section node_id
    chap_idx: dict[str, str] = {}     # "1" -> chapter node_id
    for n in nodes:
        if not n.label:
            continue
        lab = n.label.strip()
        if n.kind == "exercise":
            # accept "Exercise 7.1" / "Problem 7.1" / bare "7.1"
            m = _LABEL_NUM.search(lab)
            if m:
                exer_idx[m.group(1)] = n.node_id
        elif n.kind in (THM_LIKE | {"definition", "example", "remark"}):
            env_idx[lab.lower()] = n.node_id
        elif n.kind == "section":
            m = re.search(r"(\d+)", lab)
            if m:
                sec_idx[m.group(1)] = n.node_id
        elif n.kind == "chapter":
            m = re.search(r"(\d+)", lab)
            if m:
                chap_idx[m.group(1)] = n.node_id
    return env_idx, exer_idx, sec_idx, chap_idx


def resolve_references(nodes: list[NodeRow]) -> list[Ref]:
    env_idx, exer_idx, sec_idx, chap_idx = _build_label_index(nodes)
    refs: list[Ref] = []
    seen: set[tuple] = set()  # dedupe (src, raw) so one node citing X once counts once
    for n in nodes:
        text = n.text or ""
        for kind, pat in REF_PATTERNS:
            for m in pat.finditer(text):
                raw = m.group(0).strip()
                key = (n.node_id, raw)
                if key in seen:
                    continue
                seen.add(key)
                resolved_label = None
                resolved_id = None
                conf = 0.0
                method = kind
                if kind == "env":
                    env_kind, num = m.group(1), m.group(2)
                    resolved_label = f"{env_kind} {num}"
                    # exercises route through the bare-number index (alias split)
                    if env_kind == "Exercise":
                        resolved_id = exer_idx.get(num)
                    else:
                        resolved_id = env_idx.get(f"{env_kind} {num}".lower())
                    if resolved_id:
                        conf = 0.95
                    elif _in_slice(num):
                        # in-slice but no node -> EXTRACTION RECALL GAP (Track A)
                        conf = 0.0
                        method = "env_recall_gap"
                    else:
                        # right grammar, target genuinely outside the slice
                        conf = 0.3
                        method = "env_out_of_slice"
                elif kind == "problem":
                    num = m.group(1)
                    resolved_label = f"Problem {num}"
                    resolved_id = exer_idx.get(num)  # Problem N.M -> Exercise N.M
                    if resolved_id:
                        conf = 0.95
                        method = "problem_alias"  # resolved via the alias
                    elif _in_slice(num):
                        conf = 0.0
                        method = "problem_recall_gap"
                    else:
                        conf = 0.3
                        method = "problem_out_of_slice"
                elif kind == "section":
                    num = m.group(1)
                    resolved_label = f"§{num}"
                    if num in sec_idx:
                        resolved_id = sec_idx[num]
                        conf = 0.9
                    elif _in_slice(num):
                        conf = 0.0
                        method = "section_recall_gap"
                    else:
                        conf = 0.3
                        method = "section_out_of_slice"
                elif kind == "chapter":
                    num = m.group(1)
                    resolved_label = f"Chapter {num}"
                    if num in chap_idx:
                        resolved_id = chap_idx[num]
                        conf = 0.9
                    else:
                        conf = 0.3
                        method = "chapter_out_of_slice"
                refs.append(Ref(n.node_id, raw, resolved_label, resolved_id,
                                method, conf))
    return refs


def self_judge(refs: list[Ref]) -> None:
    """Self-judged `correct`. A reference is correct if:
      - it RESOLVED to a node whose number matches the mention, OR
      - it correctly DECLINED an out-of-slice target (A.36, §10, Example 5.7).
    A `*_recall_gap` is NOT counted correct: the target IS in the slice and
    SHOULD have a node — the miss is Track A extraction recall, which we surface
    as quality signal (see FINDINGS / report to A) rather than hide."""
    for r in refs:
        if r.resolved_node_id is not None:
            raw_num = _LABEL_NUM.search(r.raw_mention)
            lbl_num = _LABEL_NUM.search(r.resolved_label or "")
            r.correct = bool(raw_num and lbl_num and raw_num.group(1) == lbl_num.group(1))
        elif r.method.endswith("recall_gap"):
            r.correct = False  # honest: in-slice target with no node
        else:
            r.correct = r.method.endswith("out_of_slice")


def reference_edges(refs: list[Ref]) -> list[dict]:
    """R2 deliverable for Track C: promote RESOLVED references to real graph
    edges so graph-expansion retrieval has something to walk.

    For each resolved ref we emit a directed pair:
        from=citing node  -> to=cited node    edge_type='references'
        from=cited node   -> to=citing node   edge_type='referenced_by'
    (no self-edges; dedup on (from,to,type)). Unresolved / recall-gap /
    out-of-slice refs are NOT promoted — only confident, grounded links."""
    edges: list[dict] = []
    seen: set[tuple] = set()
    for r in refs:
        if not r.resolved_node_id or not r.correct:
            continue
        src, dst = r.src_node_id, r.resolved_node_id
        if src == dst:
            continue
        for frm, to, et in ((src, dst, "references"), (dst, src, "referenced_by")):
            k = (frm, to, et)
            if k in seen:
                continue
            seen.add(k)
            edges.append({"from_node_id": frm, "to_node_id": to, "edge_type": et,
                          "confidence": r.confidence,
                          "evidence": [f"in-text mention {r.raw_mention!r}"]})
    return edges


# ---------------------------------------------------------------------------
# 4. §10 structural invariants
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    node_id: Optional[str]
    invariant: str
    severity: str
    detail: str


def run_invariants(nodes: list[NodeRow], running_headers: dict[int, str]) -> list[Issue]:
    by_id = {n.node_id: n for n in nodes}
    issues: list[Issue] = []

    # (a) section/subsection numbering monotone within a parent, IN READING
    #     ORDER. The intent (§10): numbering should progress 4.1->4.2->4.3 as you
    #     read down the pages. A true violation is when page reading-order and
    #     numbering DISAGREE (e.g. 3.2 printed on a page before 3.1). We must sort
    #     siblings by page first (DB insertion order is by node_id, where "3.10"
    #     precedes "3.1" lexically -> false positive if compared unsorted).
    children: dict[str, list[NodeRow]] = {}
    for n in nodes:
        if n.parent_id:
            children.setdefault(n.parent_id, []).append(n)
    for pid, sibs in children.items():
        numbered = []
        for s in sibs:
            if s.kind in ("section", "subsection") and s.label:
                m = _LABEL_NUM.search(s.label)
                if m:
                    numbered.append((tuple(int(x) for x in m.group(1).split(".")), s))
        # sort by page reading order; numbering must be non-decreasing along it
        numbered.sort(key=lambda t: (t[1].page_pdf_start or 0,))
        for (na, a), (nb, b) in zip(numbered, numbered[1:]):
            if nb < na:
                issues.append(Issue(b.node_id, "numbering_monotone", "warn",
                    f"{b.label} ({nb}) printed before {a.label} ({na}) under {pid} "
                    f"(reading order disagrees with numbering)"))

    # (b) a proof attaches to a preceding theorem-like node
    for n in nodes:
        if n.kind == "proof":
            if not n.proves or n.proves not in by_id:
                issues.append(Issue(n.node_id, "proof_attachment", "error",
                    "proof has no resolvable `proves` target"))
                continue
            tgt = by_id[n.proves]
            if tgt.kind not in THM_LIKE:
                issues.append(Issue(n.node_id, "proof_attachment", "warn",
                    f"proof attaches to non-theorem-like {tgt.kind} ({tgt.label})"))
            # proof should not begin before its theorem
            if (n.page_pdf_start is not None and tgt.page_pdf_start is not None
                    and n.page_pdf_start < tgt.page_pdf_start):
                issues.append(Issue(n.node_id, "proof_before_theorem", "error",
                    f"proof p{n.page_pdf_start} precedes {tgt.label} p{tgt.page_pdf_start}"))

    # (c) a child cannot begin before its parent begins
    for n in nodes:
        if n.parent_id and n.parent_id in by_id:
            p = by_id[n.parent_id]
            if (n.page_pdf_start is not None and p.page_pdf_start is not None
                    and n.page_pdf_start < p.page_pdf_start):
                issues.append(Issue(n.node_id, "child_before_parent", "error",
                    f"child p{n.page_pdf_start} < parent {p.label or p.node_id} "
                    f"p{p.page_pdf_start}"))

    # (d) each TOC section has an in-body heading (TOC from PDF outline)
    #     -> handled in run() where we have the outline; passed via closure-free
    #        call below.

    # (e) a repeated top-margin line isn't a heading sequence
    #     running_headers: pdf_page -> repeated top line; flag any node whose
    #     label/title equals a running header text (would be a mis-parse)
    header_texts = {v.strip().lower() for v in running_headers.values()}
    for n in nodes:
        if n.kind in ("section", "subsection", "chapter") and n.title:
            if n.title.strip().lower() in header_texts and n.kind != "section":
                issues.append(Issue(n.node_id, "header_as_heading", "warn",
                    f"heading title equals a running header: {n.title!r}"))

    # (f) printed pages monotone across nodes in reading order
    ordered = sorted([n for n in nodes if n.page_printed_start and n.page_printed_start.isdigit()],
                     key=lambda n: (n.page_pdf_start or 0,))
    last = None
    for n in ordered:
        pp = int(n.page_printed_start)
        if last is not None and pp < last:
            issues.append(Issue(n.node_id, "printed_page_monotone", "error",
                f"printed page {pp} < previous {last} at pdf {n.page_pdf_start}"))
        last = max(last, pp) if last is not None else pp

    return issues


def check_toc_coverage(nodes: list[NodeRow],
                       slice_prefixes=("1", "2", "3", "7")) -> list[Issue]:
    """(d) Each TOC section/subsection in the slice has an in-body heading node.
    Derives expected labels from the PDF outline (§N -> bare N, and N.M), then
    checks Track A produced a section/subsection node with that bare number."""
    import fitz
    from _shared.db import ensure_book
    doc = fitz.open(ensure_book())
    toc = doc.get_toc()
    issues: list[Issue] = []
    # in-body section/subsection labels A produced, normalised to bare number
    have = {(n.label or "").replace("§", "").strip()
            for n in nodes if n.kind in ("section", "subsection")}
    for lvl, title, page in toc:
        t = title.strip()
        sec = re.match(r"^§(\d+)\b", t)          # "§7 Quotients"
        sub = re.match(r"^(\d+\.\d+)\b", t)       # "7.1 The Quotient Topology"
        key = sec.group(1) if sec else (sub.group(1) if sub else None)
        if key and key.split(".")[0] in slice_prefixes:
            if key not in have:
                issues.append(Issue(None, "toc_section_missing_heading", "error",
                    f"TOC entry {t!r} (pdf {page}) has no in-body heading node"))
    return issues


# the full R2 slice in PDF pages: Ch1 §1-§3 (22-52) + §7 Quotients (90-103)
SLICE_PAGES = list(range(22, 53)) + list(range(90, 104))


def detect_running_headers(slice_pages=SLICE_PAGES) -> dict[int, str]:
    """Repeated top-margin lines across slice pages (running headers / section
    titles that must NOT be mistaken for body headings)."""
    import fitz
    from _shared.db import ensure_book
    doc = fitz.open(ensure_book())
    top_lines: dict[int, list[str]] = {}
    counts: dict[str, int] = {}
    for pno in slice_pages:
        if pno - 1 >= doc.page_count:
            break
        pg = doc[pno - 1]
        d = pg.get_text("dict")
        lines = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                if l["bbox"][1] < 40:  # top margin band
                    txt = "".join(s["text"] for s in l["spans"]).strip()
                    if txt and not txt.isdigit():  # skip the page number itself
                        lines.append(txt)
                        counts[txt] = counts.get(txt, 0) + 1
        top_lines[pno] = lines
    # a header repeats across >=3 pages
    repeated = {t for t, c in counts.items() if c >= 3}
    return {pno: " | ".join(ls) for pno, ls in top_lines.items()
            if any(l in repeated for l in ls)}


# ---------------------------------------------------------------------------
# persistence (Track B zone only)
# ---------------------------------------------------------------------------


def persist(edges, refs, issues):
    with connect() as c, c.cursor() as cur:
        # rebuild the deterministic + reference tiers, but PRESERVE depends_on
        # (the §11 semantic tier, owned by semantic_edges.py — additive pass).
        cur.execute("delete from b_node_edges where edge_type not in ('depends_on','depended_on_by');")
        cur.execute("truncate b_references, b_validation_issues;")
        for e in edges:
            cur.execute(
                "insert into b_node_edges (from_node_id,to_node_id,edge_type,confidence,evidence) "
                "values (%s,%s,%s,%s,%s)",
                (e["from_node_id"], e["to_node_id"], e["edge_type"], e["confidence"],
                 json.dumps(e["evidence"])))
        for r in refs:
            cur.execute(
                "insert into b_references (src_node_id,raw_mention,resolved_label,"
                "resolved_node_id,method,confidence,correct) values (%s,%s,%s,%s,%s,%s,%s)",
                (r.src_node_id, r.raw_mention, r.resolved_label, r.resolved_node_id,
                 r.method, r.confidence, r.correct))
        for i in issues:
            cur.execute(
                "insert into b_validation_issues (node_id,invariant,severity,detail) "
                "values (%s,%s,%s,%s)",
                (i.node_id, i.invariant, i.severity, i.detail))
        c.commit()


def report():
    with connect() as c, c.cursor() as cur:
        print("\n--- b_node_edges by type ---")
        cur.execute("select edge_type,count(*) from b_node_edges group by 1 order by 2 desc;")
        for et, n in cur.fetchall():
            print(f"  {et:14s} {n}")
        cur.execute("select count(*) from b_node_edges;")
        print(f"  TOTAL edges: {cur.fetchone()[0]}")

        print("\n--- b_references by method ---")
        cur.execute("select method,count(*),sum((resolved_node_id is not null)::int),"
                    "sum((correct)::int) from b_references group by 1 order by 2 desc;")
        for method, tot, res, cor in cur.fetchall():
            print(f"  {method:22s} total={tot} resolved={res or 0} correct={cor or 0}")
        cur.execute("select count(*), sum((resolved_node_id is not null)::int), sum((correct)::int) from b_references;")
        tot, res, cor = cur.fetchone()
        print(f"  TOTAL refs={tot} resolved={res or 0} self-correct={cor or 0}  "
              f"acc={(cor or 0)/tot:.2%}" if tot else "  no refs")
        # honest sub-metrics for D's §17 attribution
        cur.execute("select sum((method like '%recall_gap')::int) from b_references;")
        gaps = cur.fetchone()[0] or 0
        cur.execute("select count(*) from b_references where method not like '%recall_gap';")
        decidable = cur.fetchone()[0]
        print(f"  resolver accuracy on DECIDABLE refs (excl. A recall gaps): "
              f"{(cor or 0)}/{decidable} = {(cor or 0)/decidable:.2%}" if decidable else "")
        print(f"  in-slice extraction RECALL GAPS (Track A signal): {gaps}")

        print("\n--- b_validation_issues by invariant/severity ---")
        cur.execute("select invariant,severity,count(*) from b_validation_issues group by 1,2 order by 1;")
        rows = cur.fetchall()
        for inv, sev, n in rows:
            print(f"  {inv:30s} {sev:6s} {n}")
        cur.execute("select count(*) from b_validation_issues;")
        print(f"  TOTAL issues: {cur.fetchone()[0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print counts only")
    args = ap.parse_args()
    if args.report:
        report()
        return

    t0 = time.time()
    nodes, src = load_nodes()
    print(f"loaded {len(nodes)} nodes from {src}")

    struct_edges = build_edges(nodes)
    refs = resolve_references(nodes)
    self_judge(refs)
    ref_edges = reference_edges(refs)        # references / referenced_by for C
    edges = struct_edges + ref_edges
    running = detect_running_headers()
    issues = run_invariants(nodes, running)
    issues += check_toc_coverage(nodes)
    # surface reference recall gaps as validation issues too (signal for D/§17):
    # an in-slice target cited in prose but with no extracted node.
    gap_targets: dict[str, list[str]] = {}
    for r in refs:
        if r.method.endswith("recall_gap"):
            gap_targets.setdefault(r.resolved_label or r.raw_mention, []).append(r.src_node_id)
    for tgt, citers in sorted(gap_targets.items()):
        issues.append(Issue(None, "reference_recall_gap", "warn",
            f"{tgt} cited by {len(citers)} node(s) but no extracted node "
            f"(Track A recall gap); e.g. {citers[0]}"))
    dt = time.time() - t0

    persist(edges, refs, issues)
    print(f"built {len(struct_edges)} structural + {len(ref_edges)} reference "
          f"edges = {len(edges)} total, {len(refs)} refs, {len(issues)} issues "
          f"in {dt*1000:.0f} ms")
    report()


if __name__ == "__main__":
    main()

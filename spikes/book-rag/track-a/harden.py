"""Track A — ROUND 2 hardening of the canonical `a_nodes` corpus (#57).

Closes the three R1 gaps that now matter downstream:

  1. MATH REGROUPING + vision->LaTeX. The 584 `a_equations` rows are
     per-line glyph FRAGMENTS (one display equation -> several rows, out of
     order). `regroup_equations()` clusters fragments by 2D bbox proximity into
     ORDERED display-equation REGIONS (-> the true equation count) and persists
     them to a new additive table `a_eq_regions` (raw fragment evidence in
     `a_equations` is NEVER overwritten). `vision_latex()` runs Claude vision on
     a region crop -> LaTeX, stored as `latex` + `latex_confidence`.

  2. INLINE DEFINITIONS. Tu has 0 "Definition N.M" labels for most terms — it
     defines in bold-inline prose ("A vector field ... is ..."). `inline_defs()`
     detects bold definitional runs inside section/subsection prose and emits
     them as `kind='definition'` nodes parented to their subsection.

  3. CONTRACTS for B/D. Documents the proof-node scheme and writes a normalized
     label + `aliases` onto every node (esp. proofs + exercises) so B's resolver
     and D's gold can match "Proof of Theorem 7.7" / "Problem 7.1".

Also validates the `y<35 AND size<9.5` header rule on OUT-OF-slice pages
(de-risks full-book scaling) without expanding the indexed corpus.

Additive only. New table `a_eq_regions`; new column `a_nodes.aliases` (text[]).
Run:
    cd spikes/book-rag
    BOOK_RAG_ENV=.../.env /path/.venv/bin/python track-a/harden.py [--vision N]
"""
from __future__ import annotations

import re
import sys
import json
import pathlib
import collections
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import fitz  # noqa: E402
from _shared.db import connect, ensure_book, storage_upload, load_env  # noqa: E402
import tu_config as cfg  # noqa: E402
from extract import (  # noqa: E402
    RUN_ID, SLICE_PAGES, extract_spans_and_lines, header_line, footer_line,
    _printed, detect_headers_footers,
)

# ==========================================================================
# 1. EQUATION REGROUPING — fragments -> ordered display-equation regions
# ==========================================================================
@dataclass
class EqRegion:
    region_id: str
    pdf_page: int
    bbox: list[float]                 # union bbox of members
    member_eq_ids: list[str]
    ordered_text: str                 # fragments concatenated in reading order
    parent_node_id: Optional[str]
    latex: Optional[str] = None
    latex_confidence: float = 0.2
    image_crop_key: Optional[str] = None
    n_fragments: int = 0


def _union(bboxes):
    xs0 = min(b[0] for b in bboxes); ys0 = min(b[1] for b in bboxes)
    xs1 = max(b[2] for b in bboxes); ys1 = max(b[3] for b in bboxes)
    return [round(xs0, 1), round(ys0, 1), round(xs1, 1), round(ys1, 1)]


def regroup_equations(conn):
    """Cluster `a_equations` fragments per page into ordered regions.

    Algorithm (geometric, deterministic):
      * fragments sorted by y (top), then x (left);
      * a new region starts when the vertical gap to the previous fragment's
        band exceeds V_GAP (display equations are separated by >~16pt of
        leading; sub/superscript fragments of ONE equation sit within a tight
        band). Fragments overlapping the running band merge into it.
      * within a region, members are ordered top-row then left-to-right
        (row = y within ROW_TOL) -> a best-effort linear reading order.
    """
    V_GAP = 16.0      # vertical gap (pt) that separates two display equations
    ROW_TOL = 6.0     # fragments within this y are the same visual row
    regions: list[EqRegion] = []
    with conn.cursor() as cur:
        cur.execute(
            "select eq_id, pdf_page, bbox, raw_text, parent_node_id "
            "from a_equations where run_id=%s order by pdf_page;", (RUN_ID,))
        rows = cur.fetchall()
    by_page = collections.defaultdict(list)
    for eq_id, page, bbox, raw, parent in rows:
        by_page[page].append((eq_id, [float(x) for x in bbox], raw, parent))

    for page, frags in by_page.items():
        frags.sort(key=lambda f: (round(f[1][1], 1), f[1][0]))
        clusters: list[list] = []
        cur_band_bottom = None
        for f in frags:
            y0, y1 = f[1][1], f[1][3]
            if cur_band_bottom is None or y0 - cur_band_bottom > V_GAP:
                clusters.append([f])
                cur_band_bottom = y1
            else:
                clusters[-1].append(f)
                cur_band_bottom = max(cur_band_bottom, y1)
        for i, cl in enumerate(clusters, 1):
            # order members: row (y//ROW_TOL) then x
            cl.sort(key=lambda f: (round(f[1][1] / ROW_TOL), f[1][0]))
            text = " ".join(c[2].strip() for c in cl if c[2].strip())
            parent = next((c[3] for c in cl if c[3]), None)
            regions.append(EqRegion(
                region_id=f"{RUN_ID}-p{page}-region{i}",
                pdf_page=page, bbox=_union([c[1] for c in cl]),
                member_eq_ids=[c[0] for c in cl], ordered_text=text[:1000],
                parent_node_id=parent, n_fragments=len(cl)))
    return regions


# ==========================================================================
# 2. VISION -> LaTeX on a region crop (Claude vision; OpenAI fallback)
# ==========================================================================
VISION_PROMPT = (
    "You are reading a single cropped region from a mathematics textbook "
    "(Tu, Introduction to Manifolds). It contains one or more display "
    "equations. Transcribe EXACTLY what is shown as LaTeX math. Output ONLY a "
    "JSON object: {\"latex\": \"<latex, no surrounding $>\", \"confidence\": "
    "<0..1 how sure you are it is faithful>}. If the crop is not actually math "
    "(e.g. prose), return {\"latex\": null, \"confidence\": 0.0}. No prose, JSON only."
)


def vision_latex_claude(png_bytes: bytes, model: str = "claude-opus-4-8") -> tuple[Optional[str], float]:
    """Claude vision: equation crop -> (latex, confidence). Best-effort.

    Uses the current Opus model (claude-opus-4-8) via the Messages API with a
    base64 image content block. The model id is from the claude-api skill;
    do not append a date suffix.
    """
    import base64
    import anthropic
    env = load_env()
    client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"])
    b64 = base64.standard_b64encode(png_bytes).decode()
    msg = client.messages.create(
        model=model, max_tokens=1000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": b64}},
            {"type": "text", "text": VISION_PROMPT},
        ]}])
    txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _parse_latex_json(txt)


def _parse_latex_json(txt: str) -> tuple[Optional[str], float]:
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return None, 0.0
    try:
        d = json.loads(m.group(0))
        return d.get("latex"), float(d.get("confidence", 0.0) or 0.0)
    except Exception:
        return None, 0.0


def crop_region(doc, region: EqRegion) -> bytes:
    pg = doc[region.pdf_page - 1]
    x0, y0, x1, y1 = region.bbox
    clip = fitz.Rect(max(0, x0 - 5), max(0, y0 - 4), x1 + 5, y1 + 4)
    pix = pg.get_pixmap(clip=clip, matrix=fitz.Matrix(3, 3))
    return pix.tobytes("png")


# ==========================================================================
# 3. INLINE DEFINITIONS — Tu defines terms in italic prose, not labels
# ==========================================================================
# Track C found 0 "Definition N.M" labels for most concepts: Tu introduces a
# term by *italicizing* it (LaTeX \emph) at the point of definition, usually
# after a definitional trigger phrase. We detect the trigger + the italic term.
DEF_TRIGGERS = [
    r"is called(?: the| a| an)?",
    r"are called",
    r"we call(?: the| a| an)?",
    r"is defined(?: to be| as)?",
    r"is(?: a| an)",
    r"are(?: the)?",
    r"called(?: the| a| an)",
    r"known as(?: the| a| an)?",
    r"the (?:notion|concept) of",
    r"by(?: a| an)?",  # "by a chart we mean"
    r"define(?:s|d)?(?: the| a| an)?",
]
TRIGGER_RE = re.compile(r"(?:" + r"|".join(DEF_TRIGGERS) + r")\s*$", re.IGNORECASE)
# a defining term: 1-5 alphabetic words, optionally hyphenated, no trailing punctuation noise
TERM_OK = re.compile(r"^[A-Za-z][A-Za-z\- ]{2,40}$")
# noise italic words that are statement-glue, not terms
STOPWORDS = {
    "let", "then", "if", "so", "thus", "hence", "such", "that", "where", "for",
    "and", "or", "but", "since", "because", "the", "this", "these", "those",
    "there", "here", "now", "we", "it", "is", "are", "be", "as", "an", "a",
    "of", "to", "in", "on", "with", "by", "from", "see", "note", "recall",
    "indeed", "clearly", "conversely", "moreover", "however", "first", "second",
}


@dataclass
class InlineDef:
    term: str
    pdf_page: int
    reading_order: int
    context: str           # the sentence fragment around it
    parent_node_id: Optional[str]
    confidence: float


def detect_inline_defs(doc, pages, page_info, nodes):
    """Scan body prose for italic-emphasized defined terms introduced by a
    definitional trigger. Skip the wholly-italic statements of
    theorem/lemma/example/remark/proof nodes (those italics are not terms)."""
    # map each (page, reading_order) to the containing structural/leaf node
    # by walking the same heading/env state machine cheaply: reuse a_nodes by page.
    sub_by_page = _subsection_for_page(nodes)
    out: list[InlineDef] = []
    seen_terms: set[str] = set()
    for p in pages:
        pg = doc[p - 1]
        h = pg.rect.height
        d = pg.get_text("dict")
        raw = [l for b in d["blocks"] if b.get("type") == 0 for l in b["lines"] if l["spans"]]
        raw.sort(key=lambda l: (round(l["bbox"][1], 1), l["bbox"][0]))
        for l in raw:
            y0 = l["bbox"][1]
            if y0 < cfg.HEADER_BAND_Y or y0 > h - cfg.HEADER_FOOTER_Y_BOT_MARGIN:
                continue
            spans = l["spans"]
            line_txt = cfg.normalize_text("".join(s["text"] for s in spans)).strip()
            # skip the italic *statements* of envs (whole line italic after a bold label,
            # or a continuation line of such a statement)
            if re.match(r"^(Example|Remark|Proof|Lemma|Theorem|Proposition|Corollary|Definition)\b", line_txt):
                continue
            # build running roman-text prefix to test triggers before each italic run
            prefix = ""
            for i, s in enumerate(spans):
                ital = bool(s["flags"] & 2)
                bold = bool(s["flags"] & 16)
                sz = round(s["size"], 1)
                t = cfg.normalize_text(s["text"])
                tstrip = t.strip()
                is_term_span = (ital and not bold and abs(sz - cfg.ENV_SIZE) < 0.7
                                and TERM_OK.match(tstrip))
                if is_term_span:
                    term = re.sub(r"\s+", " ", tstrip).strip().lower()
                    words = term.split()
                    # accept only if a trigger immediately precedes AND the term
                    # is a clean noun-phrase (not stopwords / hyphenation / fragment)
                    trig = bool(TRIGGER_RE.search(prefix[-40:]))
                    content_words = [w for w in words if w not in STOPWORDS]
                    hyphen_break = tstrip.endswith("-")        # "exte-" line-break artifact
                    fragment = words[-1] in STOPWORDS          # ends mid-phrase ("such that")
                    if (trig and content_words and not hyphen_break and not fragment
                            and 1 <= len(words) <= 4 and term not in seen_terms):
                        seen_terms.add(term)
                        parent = sub_by_page.get(p)
                        out.append(InlineDef(
                            term=tstrip, pdf_page=p, reading_order=int(l["bbox"][1]),
                            context=(prefix[-50:] + " [" + tstrip + "] ").strip()[:160],
                            parent_node_id=parent, confidence=0.7))
                prefix += t
    return out


def _subsection_for_page(nodes) -> dict[int, str]:
    """page -> the deepest structural node (subsection else section) whose span
    covers it; used to parent inline-def nodes."""
    by_page: dict[int, str] = {}
    structural = sorted(
        [n for n in nodes if n.kind in ("subsection", "section")],
        key=lambda n: (n.page_pdf_start or 0, 0 if n.kind == "section" else 1))
    for n in structural:
        lo = n.page_pdf_start or 0
        hi = n.page_pdf_end or lo
        for pg in range(lo, hi + 1):
            # subsection wins over section (processed later in sort)
            if pg not in by_page or n.kind == "subsection":
                by_page[pg] = n.node_id
    return by_page


# ==========================================================================
# 4. CONTRACTS for B/D — proof-node scheme + label/alias normalization
# ==========================================================================
# PROOF-NODE SCHEME (documented for Track B's resolver + Track D's gold):
#   * id pattern:  "<parent_node_id>.proof<seq>"  (seq = a global node index at
#     creation), e.g. "book.sub2.3.proof57".  Proofs are SEPARATE nodes, kind
#     'proof', label "Proof".
#   * linkage:     a proof's `proves` field holds the node_id of the immediately
#     preceding theorem-like item (theorem/proposition/lemma/corollary/
#     definition). To map a textual mention "Proof of Theorem 7.7" -> a proof
#     node: resolve "Theorem 7.7" to its node_id (via label/alias), then find the
#     proof node whose `proves` == that node_id.
#   * alias for matching: each proof gets aliases like ["Proof of Theorem 7.7",
#     "proof of 7.7"] derived from the node it proves, so B/D can match the
#     textual form directly.

def build_aliases(conn) -> dict[str, list[str]]:
    """Compute label aliases for every node so B's resolver + D's gold match
    the textual forms found in the book. Returns node_id -> [aliases]."""
    with conn.cursor() as cur:
        cur.execute(
            "select node_id, kind, label, title, proves from a_nodes where run_id=%s;",
            (RUN_ID,))
        rows = cur.fetchall()
    by_id = {r[0]: r for r in rows}
    aliases: dict[str, list[str]] = {}
    for node_id, kind, label, title, proves in rows:
        al: list[str] = []
        if label:
            al.append(label)
        # numbered envs: "Theorem 7.7" -> also bare "7.7", "Thm 7.7"
        m = re.match(r"^(Definition|Theorem|Proposition|Lemma|Corollary|Example|Remark|Exercise)\s+(\d+(?:\.\d+)*)$", label or "")
        if m:
            kw, num = m.group(1), m.group(2)
            al.append(num)
            abbr = {"Definition": "Def", "Theorem": "Thm", "Proposition": "Prop",
                    "Lemma": "Lem", "Corollary": "Cor", "Exercise": "Problem"}.get(kw)
            if abbr:
                al.append(f"{abbr} {num}")
            # exercises are referenced as "Problem N.M" in Tu's text
            if kw == "Exercise":
                al.append(f"Problem {num}")
        if title:
            al.append(title)
        # proof aliases derived from the proven node
        if kind == "proof" and proves and proves in by_id:
            _, _, plabel, ptitle, _ = by_id[proves]
            if plabel:
                al.append(f"Proof of {plabel}")
                pm = re.match(r"^\w+\s+(\d+(?:\.\d+)*)$", plabel)
                if pm:
                    al.append(f"proof of {pm.group(1)}")
        # dedup, keep order
        seen = set(); ded = []
        for a in al:
            a = a.strip()
            if a and a.lower() not in seen:
                seen.add(a.lower()); ded.append(a)
        aliases[node_id] = ded
    return aliases


# ==========================================================================
# 5. OUT-OF-SLICE validation of the header/page-top detector
# ==========================================================================
def validate_header_rule(doc, sample_pages):
    """Confirm the 'y<35 AND size<9.5' header rule generalizes off-slice:
    for each sample page, report whether the first BODY line (the line just
    below the header band) is correctly NOT classified as header, and whether
    a printed-page number was still extracted."""
    page_info, _ = detect_headers_footers(doc, sample_pages)
    results = []
    for p in sample_pages:
        pg = doc[p - 1]
        h = pg.rect.height
        d = pg.get_text("dict")
        lines = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                if l["spans"]:
                    lines.append(l)
        lines.sort(key=lambda l: round(l["bbox"][1], 1))
        # first content line below the tight header band
        first_body = next((l for l in lines if l["bbox"][1] >= cfg.HEADER_BAND_Y), None)
        fb_txt = cfg.normalize_text("".join(s["text"] for s in first_body["spans"]))[:42] if first_body else "(none)"
        fb_y = round(first_body["bbox"][1], 1) if first_body else None
        fb_sz = round(first_body["spans"][0]["size"], 1) if first_body else None
        # would the rule eat it? rule: y<HEADER_BAND_Y and size<9.5
        eaten = (fb_y is not None and fb_y < cfg.HEADER_BAND_Y and fb_sz is not None and fb_sz < 9.5)
        results.append({
            "page": p, "printed": page_info[p]["printed_page"],
            "first_body_y": fb_y, "first_body_sz": fb_sz,
            "first_body_eaten_as_header": eaten, "first_body_text": fb_txt,
        })
    return results


# ==========================================================================
# 6. persistence (ADDITIVE schema changes — announced in the report)
# ==========================================================================
DDL_ADDITIVE = """
-- regrouped, ordered display-equation regions (raw fragments in a_equations untouched)
create table if not exists book_rag_spike.a_eq_regions (
  region_id text primary key, run_id text, pdf_page int, bbox double precision[],
  member_eq_ids text[], ordered_text text, latex text, latex_confidence double precision,
  image_crop_key text, parent_node_id text, n_fragments int);
-- label aliases for B's resolver + D's gold (additive column on a_nodes)
alter table book_rag_spike.a_nodes add column if not exists aliases text[];
"""


def persist_hardening(conn, regions, inline_defs, aliases):
    import json as _json
    with conn.cursor() as cur:
        cur.execute("set local statement_timeout = '120s';")
        cur.execute(DDL_ADDITIVE)

        # equation regions (idempotent re-run)
        cur.execute("delete from a_eq_regions where run_id=%s;", (RUN_ID,))
        cur.executemany(
            "insert into a_eq_regions (region_id, run_id, pdf_page, bbox, member_eq_ids, "
            "ordered_text, latex, latex_confidence, image_crop_key, parent_node_id, n_fragments) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);",
            [(r.region_id, RUN_ID, r.pdf_page, r.bbox, r.member_eq_ids, r.ordered_text,
              r.latex, r.latex_confidence, r.image_crop_key, r.parent_node_id, r.n_fragments)
             for r in regions])

        # inline-definition nodes -> a_nodes (kind='definition', additive; remove prior inline defs first)
        cur.execute("delete from a_nodes where run_id=%s and node_id like %s;", (RUN_ID, "book.inlinedef.%"))
        for i, d in enumerate(inline_defs):
            nid = f"book.inlinedef.{i}"
            cur.execute(
                "insert into a_nodes (node_id, run_id, parent_id, kind, label, title, heading_path, "
                "page_pdf_start, page_pdf_end, text_raw, text_normalized, confidence, evidence, aliases) "
                "values (%s,%s,%s,'definition',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) "
                "on conflict (node_id) do update set parent_id=excluded.parent_id, label=excluded.label, "
                "title=excluded.title, text_normalized=excluded.text_normalized, confidence=excluded.confidence, "
                "evidence=excluded.evidence, aliases=excluded.aliases;",
                (nid, RUN_ID, d.parent_node_id, f"def: {d.term}", d.term, [],
                 d.pdf_page, d.pdf_page, d.context, d.context, d.confidence,
                 _json.dumps(["inline italic term", "trigger phrase"]), [d.term, d.term.lower()]))

        # write aliases onto every existing node
        for node_id, al in aliases.items():
            cur.execute("update a_nodes set aliases=%s where node_id=%s and run_id=%s;",
                        (al, node_id, RUN_ID))
    conn.commit()


# ==========================================================================
# main
# ==========================================================================
def main():
    import argparse
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--vision", type=int, default=0,
                    help="run Claude vision->LaTeX on N sample regions (0=skip)")
    args = ap.parse_args()

    doc = fitz.open(ensure_book())
    t0 = time.time()

    # 1. regroup equations
    with connect() as conn:
        regions = regroup_equations(conn)
    regroup_t = time.time() - t0

    # 2. inline definitions (need the structural nodes for parenting)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select node_id, kind, page_pdf_start, page_pdf_end from a_nodes "
            "where run_id=%s and kind in ('section','subsection');", (RUN_ID,))
        struct = [type("N", (), dict(node_id=r[0], kind=r[1], page_pdf_start=r[2], page_pdf_end=r[3]))()
                  for r in cur.fetchall()]
    page_info, _ = detect_headers_footers(doc, SLICE_PAGES)
    defs = detect_inline_defs(doc, SLICE_PAGES, page_info, struct)

    # 3. optional vision->LaTeX on a sample of multi-fragment regions
    vis_results = []
    if args.vision > 0:
        # pick the densest regions (most fragments) as the sample
        sample = sorted([r for r in regions if r.n_fragments >= 2],
                        key=lambda r: -r.n_fragments)[:args.vision]
        for r in sample:
            try:
                png = crop_region(doc, r)
                key = f"track-a/eqregion/{r.region_id}.png"
                storage_upload(key, png, "image/png")
                r.image_crop_key = key
                latex, conf = vision_latex_claude(png)
                r.latex, r.latex_confidence = latex, conf
                vis_results.append((r.region_id, r.n_fragments, conf, (latex or "")[:60]))
            except Exception as exc:
                vis_results.append((r.region_id, r.n_fragments, -1.0, f"ERR {exc}"))

    # 4. aliases + persist
    with connect() as conn:
        aliases = build_aliases(conn)
        persist_hardening(conn, regions, defs, aliases)

    # 5. out-of-slice validation (Ch3 §13-ish + an appendix page; do NOT index)
    oos_pages = [120, 180, 250, 300, 370]
    oos = validate_header_rule(doc, oos_pages)

    # ---- report --------------------------------------------------------
    print("=== Track A R2 hardening ===")
    nfrag = sum(r.n_fragments for r in regions)
    print(f"equation regions: {len(regions)} (from {nfrag} fragments) in {regroup_t:.2f}s")
    per_node = collections.Counter(r.parent_node_id for r in regions if r.parent_node_id)
    print(f"  regions per parent (top 5): {per_node.most_common(5)}")
    print(f"inline definitions: {len(defs)}")
    print(f"  sample terms: {[d.term for d in defs[:18]]}")
    if args.vision > 0:
        print(f"vision->LaTeX sample ({len(vis_results)} regions):")
        for rid, nf, conf, ltx in vis_results:
            print(f"  {rid} frags={nf} conf={conf:.2f} latex={ltx!r}")
    print("alias examples:")
    for nid in ("book.sec7", "book.proof" if False else None,):
        if nid and nid in aliases:
            print(f"  {nid}: {aliases[nid]}")
    # show a proof + exercise alias
    with connect() as c, c.cursor() as cur:
        cur.execute("select node_id, label, aliases from a_nodes where run_id=%s and kind='proof' and proves is not null limit 1;", (RUN_ID,))
        r = cur.fetchone()
        if r: print(f"  proof {r[0]} ({r[1]}): aliases={r[2]}")
        cur.execute("select node_id, label, aliases from a_nodes where run_id=%s and kind='exercise' limit 1;", (RUN_ID,))
        r = cur.fetchone()
        if r: print(f"  exercise {r[0]} ({r[1]}): aliases={r[2]}")
        cur.execute("select count(*) from a_nodes where run_id=%s and aliases is not null;", (RUN_ID,))
        print(f"  nodes with aliases: {cur.fetchone()[0]}")
    print("out-of-slice header-rule validation:")
    for r in oos:
        flag = "OK" if not r["first_body_eaten_as_header"] else "!! EATEN"
        print(f"  p{r['page']}: printed={r['printed']} first_body(y={r['first_body_y']},sz={r['first_body_sz']}) {flag} | {r['first_body_text']!r}")


if __name__ == "__main__":
    main()

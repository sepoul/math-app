"""Track A — structural extraction for Tu's *Introduction to Manifolds*.

Deterministic, layout-aware pipeline that turns the slice
(Ch1 §1-§3 + §7 Quotients) into the typed skeleton defined in
`_shared/schema.py`, then persists it to the `a_*` tables.

Pipeline (spec §1-§9):

  1. outline (fitz get_toc) -> a_toc_entries + slice page ranges
  2. layout-aware spans (text+font+size+bbox+bold/italic+reading_order)
     -> a_spans
  3. lines -> blocks (geometric grouping) -> a_blocks
  4. running header/footer detection (repeated text @ stable y) -> a_pages
     (also yields the per-page printed-page number, i.e. the pdf<->printed map)
  5. heading hierarchy (chapter/§section/subsection) validated vs outline
  6. formal environments (def/thm/prop/lemma/cor/proof/example/remark/exercise)
     -> a_nodes (with parent_id, heading_path, page spans, confidence, evidence,
     proof->proves linkage)
  7. display-math regions -> a_equations (raw glyph-soup + low latex_confidence)

Run:
    cd spikes/book-rag
    BOOK_RAG_ENV=.../ai-platform/.env \
      /path/to/.venv/bin/python track-a/extract.py
"""
from __future__ import annotations

import re
import sys
import pathlib
import collections
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402  (PyMuPDF)

from _shared.db import connect, ensure_book, storage_upload, SLICE  # noqa: E402
from _shared.schema import (  # noqa: E402
    Span, Block, TocEntry, Equation, Node,
)
import tu_config as cfg  # noqa: E402

RUN_ID = "track-a-r1"
BOOK_ID = "tu_manifolds"

# the shared slice -> 1-based PDF page ranges (from the outline; see FINDINGS).
# §1-§3 of Ch1 run pdf 22..52 (§4 opens at 53); §7 Quotients runs pdf 90..103
# (Chapter 3 opens at 104).
SLICE_RANGES = [(22, 52), (90, 103)]
SLICE_PAGES = [p for lo, hi in SLICE_RANGES for p in range(lo, hi + 1)]


# ==========================================================================
# 1. spans + lines
# ==========================================================================
@dataclass
class RawLine:
    pdf_page: int
    bbox: list[float]
    text: str            # normalized
    text_orig: str
    font: str            # font of the first/dominant span
    size: float
    bold: bool
    italic: bool
    is_math: bool        # any span in a math font
    reading_order: int
    x0: float = 0.0          # left edge (body margin ~42; display math indents)
    math_ratio: float = 0.0  # fraction of chars in math fonts
    span_ids: list[str] = field(default_factory=list)


def _flags(flags: int) -> tuple[bool, bool]:
    # PyMuPDF span flags: bit 1 (2) = italic, bit 4 (16) = bold (serif aside).
    return bool(flags & 16), bool(flags & 2)


def extract_spans_and_lines(doc, page: int):
    """Return (spans, lines) for one PDF page, in reading order."""
    pg = doc[page - 1]
    d = pg.get_text("dict")
    spans: list[Span] = []
    lines: list[RawLine] = []
    sidx = 0
    lorder = 0
    # collect lines with their y for reading-order sort (top->bottom, left->right)
    raw = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            sp = l["spans"]
            if not sp:
                continue
            raw.append(l)
    raw.sort(key=lambda l: (round(l["bbox"][1] / 3), l["bbox"][0]))
    for l in raw:
        sp = l["spans"]
        line_text = "".join(s["text"] for s in sp)
        if not line_text.strip():
            continue
        s0 = sp[0]
        bold0, ital0 = _flags(s0["flags"])

        def _ismf(f):
            return any(f.startswith(h) or h in f for h in cfg.MATH_FONT_HINTS)
        is_math = any(_ismf(s["font"]) for s in sp)
        _tot = sum(len(s["text"]) for s in sp) or 1
        _mch = sum(len(s["text"]) for s in sp if _ismf(s["font"]))
        math_ratio = _mch / _tot
        sids = []
        for s in sp:
            sb, si = _flags(s["flags"])
            sid = f"{RUN_ID}-p{page}-s{sidx}"
            sidx += 1
            sids.append(sid)
            spans.append(Span(
                pdf_page=page, bbox=[round(x, 1) for x in s["bbox"]],
                text=cfg.strip_ctrl(s["text"]), font=s["font"], font_size=round(s["size"], 2),
                bold=sb, italic=si, reading_order=lorder, confidence=0.99,
            ))
        lines.append(RawLine(
            pdf_page=page, bbox=[round(x, 1) for x in l["bbox"]],
            text=cfg.normalize_text(line_text), text_orig=cfg.strip_ctrl(line_text),
            font=s0["font"], size=round(s0["size"], 1),
            bold=bold0, italic=ital0, is_math=is_math,
            reading_order=lorder, x0=round(l["bbox"][0], 1),
            math_ratio=round(math_ratio, 2), span_ids=sids,
        ))
        lorder += 1
    return spans, lines


# ==========================================================================
# 2. running header / footer detection + printed-page mapping
# ==========================================================================
def detect_headers_footers(doc, pages: list[int]):
    """Repeated top/bottom-margin text at a stable y across pages -> header/footer.

    Returns (header_line_ids, footer_line_ids, page_info) where page_info maps
    pdf_page -> {"printed_page", "has_header", "has_footer", "header_text"}.
    The printed page number is the integer token sitting in the running header.
    """
    # gather margin TOKENS (with x) per page so we can locate the page-number
    # token by its position in the outer margin (Tu prints it at the far edge:
    # left token on even pages, right token on odd pages).
    margin = {}   # pdf_page -> {"top":[(x0,x1,y0,text)], "bot":[...], "width":W}
    for p in pages:
        pg = doc[p - 1]
        h = pg.rect.height
        w = pg.rect.width
        d = pg.get_text("dict")
        tops, bots = [], []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    txt = cfg.normalize_text(s["text"]).strip()
                    if not txt:
                        continue
                    x0, y0, x1, _ = s["bbox"]
                    if y0 < cfg.HEADER_FOOTER_Y_TOP:
                        tops.append((round(x0), round(x1), round(y0, 1), txt))
                    elif y0 > h - cfg.HEADER_FOOTER_Y_BOT_MARGIN:
                        bots.append((round(x0), round(x1), round(y0, 1), txt))
        margin[p] = {"top": sorted(tops), "bot": sorted(bots), "width": w}

    page_info = {}
    for p in pages:
        mp = margin[p]
        w = mp["width"]
        hdr = [t for t in mp["top"] if t[2] < 35]
        info = {"printed_page": _page_number_token(hdr, w),
                "has_header": bool(hdr),
                "has_footer": bool(mp["bot"]),
                "header_text": " ".join(t[3] for t in hdr) or None}
        # chapter-opener pages have no running header; printed no. is in footer
        if info["printed_page"] is None and mp["bot"]:
            info["printed_page"] = _page_number_token(mp["bot"], w)
        page_info[p] = info
    return page_info, margin


def _page_number_token(toks, page_width: float):
    """The printed page number is a standalone integer sitting in the OUTER
    margin of the running header (left edge on even pages, right edge on odd).
    Tu's inner tokens are the section glyph "§ N" / subsection "N.M" / title —
    never a bare 1-3 digit integer at the page edge."""
    ints = [(x0, x1, txt) for (x0, x1, _, txt) in toks if re.fullmatch(r"\d{1,3}", txt)]
    if not ints:
        return None
    # prefer the integer closest to a page edge (min x0, or max x1)
    left = min(ints, key=lambda t: t[0])
    right = max(ints, key=lambda t: t[1])
    if left[0] < 60:          # far-left -> even/left page number
        return left[2]
    if right[1] > page_width - 60:  # far-right -> odd/right page number
        return right[2]
    return left[2]            # fallback: the leftmost integer


def header_line(line: RawLine) -> bool:
    """Is this line a running header? Must be in the TIGHT stable-y band AND
    small (<9.5pt). The two-part test matters: body theorem labels open a page
    at y~=47 in 10pt and must NOT be eaten as header."""
    return line.bbox[1] < cfg.HEADER_BAND_Y and line.size < 9.5


def footer_line(doc, line: RawLine) -> bool:
    h = doc[line.pdf_page - 1].rect.height
    return line.bbox[1] > h - cfg.HEADER_FOOTER_Y_BOT_MARGIN


# ==========================================================================
# 3. heading + environment classification
# ==========================================================================
@dataclass
class Heading:
    pdf_page: int
    kind: str           # "chapter" | "section" | "subsection"
    number: str         # "1" | "7" | "1.1"
    title: str
    reading_order: int
    confidence: float
    evidence: list[str]


@dataclass
class EnvHit:
    pdf_page: int
    reading_order: int
    kind: str           # definition/theorem/.../proof/example/remark/exercise
    label: Optional[str]
    number: Optional[str]
    title: Optional[str]
    first_line: str
    confidence: float
    evidence: list[str]


def classify_heading(line: RawLine, in_problems: bool) -> Optional[Heading]:
    t = line.text.strip()
    # section: "§N Title"  (the § may render bold ~14.3, or the § glyph leads)
    m = cfg.SECTION_RE.match(t)
    if m and (line.bold or line.size >= cfg.SECTION_SIZE_MIN):
        ev = ["matched §N pattern"]
        if line.size >= cfg.SECTION_SIZE_MIN:
            ev.append(f"font {line.size}pt >= section threshold")
        if line.bold:
            ev.append("bold")
        return Heading(line.pdf_page, "section", m.group("num"),
                       cfg.normalize_text(m.group("title")).strip(),
                       line.reading_order, 0.95, ev)
    # chapter opener: "Chapter K"
    m = cfg.CHAPTER_RE.match(t)
    if m and (line.bold or line.size >= cfg.CHAPTER_SIZE_MIN):
        return Heading(line.pdf_page, "chapter", m.group("num"),
                       cfg.normalize_text(m.group("title")).strip(),
                       line.reading_order, 0.9,
                       ["matched Chapter K pattern",
                        f"font {line.size}pt"])
    # subsection: "N.M Title" in bold ~12pt (NOT inside Problems, NOT "Problems")
    if line.bold and abs(line.size - cfg.SUBSECTION_SIZE) < 0.6 and not in_problems:
        if cfg.PROBLEMS_RE.match(t):
            return None
        m = cfg.SUBSECTION_RE.match(t)
        if m:
            return Heading(line.pdf_page, "subsection", m.group("num"),
                           m.group("title").strip(), line.reading_order, 0.93,
                           ["matched N.M pattern", "bold 12pt"])
    return None


def classify_env(line: RawLine, in_problems: bool) -> Optional[EnvHit]:
    t = line.text.strip()
    # ----- INLINE exercises (anywhere in the body): bold-9 "Exercise N.M ..." -
    # Tu interleaves these in the prose, NOT under a Problems block, so this is
    # not gated on in_problems. The explicit "Exercise" keyword + bold-9 makes
    # it unambiguous (figures are excluded; figure lines never start "Exercise").
    if line.bold and abs(line.size - cfg.EXERCISE_SIZE) < 0.6:
        mi = cfg.INLINE_EXERCISE_RE.match(t)
        if mi:
            title = (mi.group("title") or "").strip()[:80]
            return EnvHit(line.pdf_page, line.reading_order, "exercise",
                          f"Exercise {mi.group('num')}", mi.group("num"),
                          title or None, t, 0.9,
                          ["bold 9pt", "inline Exercise keyword"])
    # ----- in-Problems exercises: bold-9 "N.M. title", exclude figures -----
    if (line.bold and abs(line.size - cfg.EXERCISE_SIZE) < 0.6
            and in_problems and not cfg.FIGURE_RE.match(t)):
        m = cfg.EXERCISE_RE.match(t)
        if m:
            return EnvHit(line.pdf_page, line.reading_order, "exercise",
                          f"Exercise {m.group('num')}", m.group("num"),
                          m.group("title").strip()[:80], t, 0.9,
                          ["bold 9pt under Problems", "matched N.M. exercise"])
    # ----- bold-10 environments: def/thm/prop/lemma/cor --------------------
    if line.bold and abs(line.size - cfg.ENV_SIZE) < 0.7:
        for kind, rx in cfg.ENV_BOLD_10.items():
            if re.match(rx, t):
                return _label_hit(line, kind, t,
                                  ["bold 10pt", f"keyword {kind}"], 0.95)
    # ----- italic-10 environments: proof/example/remark -------------------
    if line.italic and abs(line.size - cfg.ENV_SIZE) < 0.7:
        for kind, rx in cfg.ENV_ITALIC_10.items():
            if re.match(rx, t):
                conf = 0.95 if kind == "proof" else 0.93
                return _label_hit(line, kind, t,
                                  ["italic 10pt", f"keyword {kind}"], conf)
    return None


def _label_hit(line: RawLine, kind: str, t: str, ev: list[str], conf: float) -> EnvHit:
    lm = cfg.LABEL_RE.match(t)
    num = lm.group("num") if lm else None
    title = lm.group("title") if lm else None
    if kind == "proof":
        label = "Proof"
    else:
        label = f"{kind.capitalize()}" + (f" {num}" if num else "")
    return EnvHit(line.pdf_page, line.reading_order, kind, label, num,
                  (cfg.normalize_text(title).strip() if title else None),
                  t, conf, ev)


# ==========================================================================
# 4. outline (TOC) -> TocEntry rows + slice expectation
# ==========================================================================
def parse_outline(doc) -> list[TocEntry]:
    """fitz get_toc(simple=False) -> normalized TocEntry rows.

    Tu's outline is clean L1/L2/L3 = Chapter / §Section / Subsection|Problems.
    """
    entries: list[TocEntry] = []
    for lvl, title, page, *_ in doc.get_toc(simple=False):
        t = cfg.normalize_text(title.replace("\r", " ").replace("\\r", " ")).strip()
        chapter_no = section_no = None
        clean_title = t
        if lvl == 1:
            m = cfg.CHAPTER_RE.match(t)
            if m:
                chapter_no = int(m.group("num"))
                clean_title = m.group("title").strip()
        elif lvl == 2:
            m = cfg.SECTION_RE.match(t)
            if m:
                section_no = m.group("num")
                clean_title = m.group("title").strip()
        elif lvl == 3:
            m = cfg.SUBSECTION_RE.match(t)
            if m:
                section_no = m.group("num")
                clean_title = m.group("title").strip()
        entries.append(TocEntry(
            level=lvl, raw_label=t, chapter_number=chapter_no,
            section_number=section_no, title=clean_title, pdf_page=page,
        ))
    return entries


def slice_outline(entries: list[TocEntry]) -> list[TocEntry]:
    return [e for e in entries if e.pdf_page in SLICE_PAGES]


# ==========================================================================
# 5. node assembly — hierarchy + environments with boundaries & linkage
# ==========================================================================
@dataclass
class PageData:
    pdf_page: int
    lines: list[RawLine]
    in_problems_at: dict[int, bool] = field(default_factory=dict)  # reading_order -> in Problems block


def _printed(page_info, p) -> Optional[str]:
    return page_info.get(p, {}).get("printed_page")


def build_nodes(doc, pages, page_info, outline) -> tuple[list[Node], list[Equation], list[Block]]:
    """Single sequential pass across the slice's reading order to build the
    structural tree + environment leaves + equation regions."""
    # gather all content lines (drop header/footer) in document order
    seq: list[RawLine] = []
    blocks: list[Block] = []
    eqs: list[Equation] = []
    for p in pages:
        _spans, lines = extract_spans_and_lines(doc, p)
        for ln in lines:
            if header_line(ln) or footer_line(doc, ln):
                continue
            seq.append(ln)

    # mark Problems regions: once "Problems" header seen on a page, subsequent
    # lines (until next §/chapter heading) are inside a Problems block.
    in_problems = False
    for ln in seq:
        t = ln.text.strip()
        if cfg.SECTION_RE.match(t) and (ln.bold or ln.size >= cfg.SECTION_SIZE_MIN):
            in_problems = False
        if cfg.CHAPTER_RE.match(t) and (ln.bold or ln.size >= cfg.CHAPTER_SIZE_MIN):
            in_problems = False
        ln_in_problems = in_problems
        if cfg.PROBLEMS_RE.match(t) and ln.bold and abs(ln.size - cfg.SUBSECTION_SIZE) < 0.6:
            in_problems = True
        ln.__dict__["_in_problems"] = ln_in_problems

    nodes: list[Node] = []
    # hierarchy stack: chapter -> section -> subsection (by node_id)
    cur_chapter: Optional[Node] = None
    cur_section: Optional[Node] = None
    cur_subsection: Optional[Node] = None
    cur_env: Optional[Node] = None
    last_thm_like: Optional[Node] = None   # for proof->proves linkage
    eq_counter = collections.Counter()

    def heading_path() -> list[str]:
        hp = []
        # chapter for the path is the current SECTION's parent chapter (from the
        # outline), not the last in-body chapter opener — handles the §7 case.
        ch_title = None
        if cur_section and cur_section.parent_id:
            ch_title = _chapter_title(outline, cur_section.parent_id)
        if ch_title is None and cur_chapter:
            ch_title = cur_chapter.title or cur_chapter.label
        if ch_title:
            hp.append(ch_title)
        if cur_section:
            hp.append(f"§{cur_section.label} {cur_section.title}".strip()
                      if cur_section.label else (cur_section.title or ""))
        if cur_subsection:
            hp.append(f"{cur_subsection.label} {cur_subsection.title}".strip()
                      if cur_subsection.label else (cur_subsection.title or ""))
        return [h for h in hp if h]

    def close_env(end_page: int):
        nonlocal cur_env
        if cur_env is not None:
            cur_env.page_pdf_end = end_page
            cur_env.page_printed_end = _printed(page_info, end_page)
            cur_env = None

    THM_LIKE = {"theorem", "proposition", "lemma", "corollary", "definition"}

    for ln in seq:
        t = ln.text.strip()
        ip = ln.__dict__.get("_in_problems", False)

        # ---- display-math fragment? --------------------------------------
        # Tu's display math comes out as fragmented glyph-runs on shifted
        # baselines (sub/superscripts, fraction numerators) -> one display
        # equation becomes SEVERAL rows, out of order. We flag a line as a
        # display-math FRAGMENT when it is either strongly math (ratio>=0.45)
        # OR indented past the body margin AND moderately math (x0>=90 &
        # ratio>=0.2). This cuts prose-with-inline-math false positives (e.g.
        # "subset U of Rn star-shaped..." @ ratio 0.14, x0=42). The HARD part —
        # regrouping fragments into ordered regions / LaTeX — is left to a
        # later pass; latex_confidence stays low. (See FINDINGS: math is the
        # break point.)
        is_label = ln.bold and ln.size >= cfg.ENV_SIZE - 0.5
        frag = ln.is_math and not is_label and len(t) >= 2 and (
            ln.math_ratio >= 0.45 or (ln.x0 >= 90 and ln.math_ratio >= 0.20))
        if frag:
            eq_counter[ln.pdf_page] += 1
            eid = f"{RUN_ID}-p{ln.pdf_page}-eq{eq_counter[ln.pdf_page]}"
            parent = cur_env or cur_subsection or cur_section
            eqs.append(Equation(
                eq_id=eid, pdf_page=ln.pdf_page, bbox=ln.bbox,
                raw_text=ln.text_orig[:500], latex=None, latex_confidence=0.2,
                parent_node_id=(parent.node_id if parent else None),
            ))
            if cur_env is not None:
                cur_env.math_region_ids.append(eid)
            # fall through: math lines also extend the current env text

        # ---- heading? -----------------------------------------------------
        h = classify_heading(ln, ip)
        if h is not None:
            close_env(ln.pdf_page)
            if h.kind == "chapter":
                # title from outline if missing
                if not h.title:
                    for e in outline:
                        if e.level == 1 and e.chapter_number == int(h.number):
                            h.title = e.title
                            break
                nid = f"book.ch{h.number}"
                cur_chapter = Node(
                    node_id=nid, parent_id="book", kind="chapter",
                    label=f"Chapter {h.number}", title=h.title,
                    heading_path=[h.title or f"Chapter {h.number}"],
                    page_pdf_start=h.pdf_page, page_printed_start=_printed(page_info, h.pdf_page),
                    confidence=h.confidence, evidence=h.evidence)
                nodes.append(cur_chapter)
                cur_section = cur_subsection = None
                last_thm_like = None
            elif h.kind == "section":
                # validate vs outline; fill title if body title weak
                otitle = None
                for e in outline:
                    if e.level == 2 and e.section_number == h.number:
                        otitle = e.title
                        break
                title = h.title or otitle or ""
                ev = list(h.evidence)
                if otitle:
                    ev.append("matched outline §-entry")
                    h.confidence = min(0.99, h.confidence + 0.03)
                nid = f"book.sec{h.number}"
                # parent chapter is authoritative from the OUTLINE: Tu's section
                # numbering is continuous book-wide, so §7 lives under Chapter 2
                # even though the slice's only in-body chapter opener is Ch1.
                pid = _chapter_for_section(outline, h.number) or (cur_chapter.node_id if cur_chapter else None)
                ch_title = _chapter_title(outline, pid)
                cur_section = Node(
                    node_id=nid, parent_id=pid, kind="section",
                    label=h.number, title=title,
                    heading_path=([ch_title] if ch_title else []) + [f"§{h.number} {title}".strip()],
                    page_pdf_start=h.pdf_page, page_printed_start=_printed(page_info, h.pdf_page),
                    confidence=h.confidence, evidence=ev)
                nodes.append(cur_section)
                cur_subsection = None
                last_thm_like = None
            elif h.kind == "subsection":
                otitle = None
                for e in outline:
                    if e.level == 3 and e.section_number == h.number:
                        otitle = e.title
                        break
                title = h.title or otitle or ""
                ev = list(h.evidence)
                if otitle:
                    ev.append("matched outline subsection-entry")
                nid = f"book.sub{h.number}"
                pid = cur_section.node_id if cur_section else None
                cur_subsection = Node(
                    node_id=nid, parent_id=pid, kind="subsection",
                    label=h.number, title=title,
                    page_pdf_start=h.pdf_page, page_printed_start=_printed(page_info, h.pdf_page),
                    confidence=h.confidence, evidence=ev)
                # heading_path() now resolves the chapter from cur_section's parent
                cur_subsection.heading_path = heading_path()
                nodes.append(cur_subsection)
                last_thm_like = None
            continue

        # ---- environment label? ------------------------------------------
        e = classify_env(ln, ip)
        if e is not None:
            close_env(ln.pdf_page)
            parent = cur_subsection or cur_section or cur_chapter
            seqno = len(nodes)
            nid = f"{(parent.node_id if parent else 'book')}.{e.kind}{seqno}"
            node = Node(
                node_id=nid, parent_id=(parent.node_id if parent else None),
                kind=e.kind, label=e.label, title=e.title,
                heading_path=heading_path(),
                page_pdf_start=e.pdf_page, page_printed_start=_printed(page_info, e.pdf_page),
                text_raw=ln.text_orig, text_normalized=t,
                confidence=e.confidence, evidence=e.evidence)
            if e.kind == "proof":
                if last_thm_like is not None:
                    node.proves = last_thm_like.node_id
                    node.evidence = node.evidence + [f"attached to preceding {last_thm_like.kind} {last_thm_like.label}"]
                else:
                    node.confidence = min(node.confidence, 0.6)
                    node.evidence = node.evidence + ["no preceding theorem-like item to attach"]
            nodes.append(node)
            cur_env = node
            if e.kind in THM_LIKE:
                last_thm_like = node
            continue

        # ---- continuation of current env: extend text & end page ---------
        if cur_env is not None:
            cur_env.text_raw = (cur_env.text_raw or "") + " " + ln.text_orig
            cur_env.text_normalized = (cur_env.text_normalized or "") + " " + t
            cur_env.page_pdf_end = ln.pdf_page
            cur_env.page_printed_end = _printed(page_info, ln.pdf_page)

    close_env(pages[-1])

    # synthesize any chapter node referenced by a slice section whose opener
    # page is outside the slice (e.g. §7 -> Chapter 2, opener at pdf 66).
    have = {n.node_id for n in nodes}
    needed = {n.parent_id for n in nodes if n.kind == "section" and n.parent_id}
    for cid in sorted(needed - have):
        path_title = _chapter_title(outline, cid)   # "Chapter 2: Manifolds"
        opener = bare = None
        for e in outline:
            if e.level == 1 and f"book.ch{e.chapter_number}" == cid:
                opener, bare = e.pdf_page, e.title   # bare = "Manifolds"
                break
        nodes.insert(0, Node(
            node_id=cid, parent_id="book", kind="chapter",
            label=cid.replace("book.ch", "Chapter "), title=bare,
            heading_path=[path_title] if path_title else [],
            page_pdf_start=opener, page_printed_start=None,
            confidence=0.85,
            evidence=["synthesized from outline (opener outside slice)"]))

    # set page_pdf_end for hierarchy nodes (until next sibling/parent start)
    _close_hierarchy_spans(nodes, pages[-1], page_info)
    return nodes, eqs, blocks


def _chapter_for_section(outline, section_num: str) -> Optional[str]:
    """Find which chapter a §N belongs to, from the outline ordering."""
    cur_ch = None
    for e in outline:
        if e.level == 1 and e.chapter_number is not None:
            cur_ch = e.chapter_number
        elif e.level == 2 and e.section_number == section_num:
            return f"book.ch{cur_ch}" if cur_ch else None
    return None


def _chapter_title(outline, chapter_node_id: Optional[str]) -> Optional[str]:
    """'book.ch2' -> 'Chapter 2: Manifolds' (title from the outline)."""
    if not chapter_node_id or not chapter_node_id.startswith("book.ch"):
        return None
    try:
        num = int(chapter_node_id.split("book.ch")[1])
    except ValueError:
        return None
    for e in outline:
        if e.level == 1 and e.chapter_number == num:
            return f"Chapter {num}: {e.title}".strip().rstrip(":")
    return f"Chapter {num}"


def _close_hierarchy_spans(nodes, last_page, page_info):
    structural = [n for n in nodes if n.kind in ("chapter", "section", "subsection")]
    for i, n in enumerate(structural):
        # ends right before the next structural node of equal-or-higher level
        end = last_page
        for m in structural[i + 1:]:
            order = {"chapter": 0, "section": 1, "subsection": 2}
            if order[m.kind] <= order[n.kind]:
                end = max(n.page_pdf_start, m.page_pdf_start - 1) if m.page_pdf_start > n.page_pdf_start else m.page_pdf_start
                break
        n.page_pdf_end = end
        n.page_printed_end = _printed(page_info, end)


# ==========================================================================
# 6. persistence
# ==========================================================================
def persist(conn, run_id, outline, page_info, all_spans, all_lines, nodes, eqs):
    with conn.cursor() as cur:
        # generous per-session timeout for the bulk write (default is 2min and
        # the slice carries ~5k spans); keeps the txn short anyway via batching.
        cur.execute("set local statement_timeout = '120s';")
        # wipe prior rows for this run (idempotent re-run)
        for t in ("a_equations", "a_nodes", "a_toc_entries", "a_blocks",
                  "a_spans", "a_pages", "a_parse_runs"):
            cur.execute(f"delete from {t} where run_id=%s;", (run_id,))

        cur.execute(
            "insert into a_parse_runs (run_id, book, slice, tool, notes) "
            "values (%s,%s,%s,%s,%s::jsonb);",
            (run_id, BOOK_ID, SLICE, "pymupdf",
             '{"pipeline":"deterministic layout+typography","slice_ranges":"22-52,90-103"}'))

        cur.executemany(
            "insert into a_pages (run_id, pdf_page, printed_page, has_header, has_footer, meta) "
            "values (%s,%s,%s,%s,%s,%s::jsonb);",
            [(run_id, p, info["printed_page"], info["has_header"], info["has_footer"],
              _json({"header_text": info["header_text"]})) for p, info in page_info.items()])

        cur.executemany(
            "insert into a_spans (run_id, pdf_page, bbox, text, font, font_size, bold, italic, "
            "reading_order, source, confidence) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);",
            [(run_id, sp.pdf_page, sp.bbox, sp.text, sp.font, sp.font_size, sp.bold,
              sp.italic, sp.reading_order, sp.source, sp.confidence) for sp in all_spans])

        # blocks = one row per content line (geometric block grouping kept simple)
        cur.executemany(
            "insert into a_blocks (block_id, run_id, pdf_page, bbox, kind, text_raw, "
            "span_ids, reading_order, confidence) values (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "on conflict (block_id) do nothing;",
            [(f"{run_id}-p{ln.pdf_page}-b{ln.reading_order}", run_id, ln.pdf_page, ln.bbox,
              "line", ln.text_orig[:2000], ln.span_ids, ln.reading_order, 0.95)
             for ln in all_lines])

        cur.executemany(
            "insert into a_toc_entries (run_id, level, raw_label, chapter_number, "
            "section_number, title, pdf_page, printed_page) values (%s,%s,%s,%s,%s,%s,%s,%s);",
            [(run_id, e.level, e.raw_label, e.chapter_number, e.section_number,
              e.title, e.pdf_page, e.printed_page) for e in outline])

        for n in nodes:
            cur.execute(
                "insert into a_nodes (node_id, run_id, parent_id, kind, label, title, heading_path, "
                "page_pdf_start, page_pdf_end, page_printed_start, page_printed_end, text_raw, "
                "text_normalized, proves, math_region_ids, confidence, evidence) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
                "on conflict (node_id) do update set "
                "parent_id=excluded.parent_id, kind=excluded.kind, label=excluded.label, "
                "title=excluded.title, heading_path=excluded.heading_path, "
                "page_pdf_start=excluded.page_pdf_start, page_pdf_end=excluded.page_pdf_end, "
                "page_printed_start=excluded.page_printed_start, page_printed_end=excluded.page_printed_end, "
                "text_raw=excluded.text_raw, text_normalized=excluded.text_normalized, "
                "proves=excluded.proves, math_region_ids=excluded.math_region_ids, "
                "confidence=excluded.confidence, evidence=excluded.evidence;",
                (n.node_id, run_id, n.parent_id, n.kind, n.label, n.title, n.heading_path,
                 n.page_pdf_start, n.page_pdf_end, n.page_printed_start, n.page_printed_end,
                 (n.text_raw or "")[:8000], (n.text_normalized or "")[:8000], n.proves,
                 n.math_region_ids, n.confidence, _json(n.evidence)))

        for q in eqs:
            cur.execute(
                "insert into a_equations (eq_id, run_id, pdf_page, bbox, raw_text, latex, "
                "latex_confidence, image_crop_key, parent_node_id, block_id) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (eq_id) do nothing;",
                (q.eq_id, run_id, q.pdf_page, q.bbox, q.raw_text, q.latex,
                 q.latex_confidence, q.image_crop_key, q.parent_node_id, q.block_id))
    conn.commit()


def _json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def _upload_equation_crops(doc, eqs, sample_pages=()):
    """Render a tight crop around each flagged display-math fragment on a few
    sample pages and upload to the bucket (track-a/eq/...). Sets image_crop_key
    on those Equation rows. Best-effort: any failure (no network) is swallowed
    so extraction never blocks on storage."""
    n = 0
    by_page = collections.defaultdict(list)
    for q in eqs:
        if q.pdf_page in sample_pages and q.bbox:
            by_page[q.pdf_page].append(q)
    for p, qs in by_page.items():
        try:
            pg = doc[p - 1]
            for q in qs:
                x0, y0, x1, y1 = q.bbox
                clip = fitz.Rect(max(0, x0 - 4), max(0, y0 - 3), x1 + 4, y1 + 3)
                pix = pg.get_pixmap(clip=clip, matrix=fitz.Matrix(2, 2))
                key = f"track-a/eq/{q.eq_id}.png"
                storage_upload(key, pix.tobytes("png"), "image/png")
                q.image_crop_key = key
                n += 1
        except Exception as exc:  # network/storage best-effort
            print(f"[warn] crop upload skipped for p{p}: {exc}")
            break
    return n


# ==========================================================================
# main
# ==========================================================================
def main():
    import time
    t0 = time.time()
    doc = fitz.open(ensure_book())

    outline = parse_outline(doc)
    sl_outline = slice_outline(outline)

    page_info, _margin = detect_headers_footers(doc, SLICE_PAGES)

    all_spans, all_lines = [], []
    for p in SLICE_PAGES:
        spans, lines = extract_spans_and_lines(doc, p)
        all_spans.extend(spans)
        all_lines.extend(lines)

    nodes, eqs, _blocks = build_nodes(doc, SLICE_PAGES, page_info, outline)
    elapsed = time.time() - t0

    # demonstrate page-region crops -> bucket for two equation-heavy pages, so
    # Track C/D have a visual evidence path for the (low-confidence) math regions.
    ncrops = _upload_equation_crops(doc, eqs, sample_pages=(25, 91))

    with connect() as conn:
        persist(conn, RUN_ID, outline, page_info, all_spans, all_lines, nodes, eqs)

    # ---- report --------------------------------------------------------
    kinds = collections.Counter(n.kind for n in nodes)
    print(f"=== Track A extract — {SLICE} ===")
    print(f"slice pages (pdf): {SLICE_PAGES[0]}..{SLICE_PAGES[-1]} "
          f"(+gap), {len(SLICE_PAGES)} pages")
    print(f"extraction time: {elapsed:.2f}s ({elapsed/len(SLICE_PAGES)*1000:.0f}ms/page; "
          f"~{elapsed/len(SLICE_PAGES)*430:.1f}s for 430pp)")
    print(f"outline entries: {len(outline)} total / {len(sl_outline)} in slice")
    print(f"spans: {len(all_spans)}  content-lines(blocks): {len(all_lines)}")
    print(f"nodes: {len(nodes)} -> {dict(kinds)}")
    print(f"equations: {len(eqs)} (display-math fragments; {ncrops} crops uploaded to track-a/eq/)")
    # printed-page map sanity
    mapped = [(p, page_info[p]['printed_page']) for p in SLICE_PAGES if page_info[p]['printed_page']]
    print(f"printed-page map: {len(mapped)}/{len(SLICE_PAGES)} pages mapped; "
          f"samples {mapped[:3]} ... {mapped[-2:]}")


if __name__ == "__main__":
    main()

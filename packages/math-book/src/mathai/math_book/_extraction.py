"""Deterministic structural extraction — ported from spike Track A.

Provenance: adapted from
  `origin/spike/extraction-skeleton:spikes/book-rag/track-a/tu_config.py`
  `origin/spike/extraction-skeleton:spikes/book-rag/track-a/extract.py`

The spike wrote to isolated `a_*` Postgres tables and was hardwired to L. W.
Tu's *Introduction to Manifolds* slice; this module keeps the SAME deterministic
layout+typography pipeline but returns in-memory values — a page map + a list of
`ParsedNode`/`ParsedEquation` (plain dataclasses) namespaced by nothing (the
caller stamps `book_id` into `BookNode.node_id`). No DB, no bucket, no slice
hardcoding: it parses whatever page range it's handed.

The typography thresholds are Tu-calibrated (the spike's central learning: Tu's
headings/environments separate by FONT + SIZE, not regex alone). They remain the
v1 defaults; a later issue can lift them into per-book config. Vision→LaTeX for
the flagged display-math regions stays OUT of this hot path (the spike left
`latex_confidence` low and deferred it) — equations are captured as raw
glyph-runs only.

`fitz` (PyMuPDF) is imported lazily inside `parse_pdf` so this module imports
without the execution extra present (mirrors how math_notes defers its media
deps).
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    import fitz


# ============================================================================
# config — ported verbatim from track-a/tu_config.py (Tu-calibrated typography)
# ============================================================================
BODY_SIZE = 10.0
CHAPTER_SIZE_MIN = 13.5
SECTION_SIZE_MIN = 13.5
SUBSECTION_SIZE = 12.0
ENV_SIZE = 10.0
EXERCISE_SIZE = 9.0

HEADER_FOOTER_Y_TOP = 60.0
HEADER_BAND_Y = 35.0
HEADER_FOOTER_Y_BOT_MARGIN = 45.0

ENV_BOLD_10 = {
    "definition": r"^Definition\b",
    "theorem": r"^Theorem\b",
    "proposition": r"^Proposition\b",
    "lemma": r"^Lemma\b",
    "corollary": r"^Corollary\b",
}
ENV_ITALIC_10 = {
    "proof": r"^Proof\b",
    "example": r"^Example\b",
    "remark": r"^Remark\b",
}

LABEL_RE = re.compile(
    r"^(?P<kw>Definition|Theorem|Proposition|Lemma|Corollary|Example|Remark|Exercise)"
    r"(?:\s+(?P<num>\d+(?:\.\d+)*)\*?)?"
    r"(?:\s*\((?P<title>[^)]*)\))?"
)
EXERCISE_RE = re.compile(r"^(?P<num>\d+\.\d+)\.(?P<star>\*)?\s+(?P<title>.+)$")
INLINE_EXERCISE_RE = re.compile(
    r"^Exercise\s+(?P<num>\d+\.\d+)\*?(?:\s*\((?P<title>[^)]*)\))?")
FIGURE_RE = re.compile(r"^Fig(?:ure)?\.?\s", re.IGNORECASE)
SECTION_RE = re.compile(r"^§\s*(?P<num>\d+)\b\s*(?P<title>.*)$")
CHAPTER_RE = re.compile(r"^Chapter\s+(?P<num>\d+)\b\s*:?\s*(?P<title>.*)$")
SUBSECTION_RE = re.compile(r"^(?P<num>\d+\.\d+)\s+(?P<title>\D.*)$")
PROBLEMS_RE = re.compile(r"^Problems\s*$")

MATH_FONT_HINTS = ("CMR", "CMMI", "CMSY", "CMEX", "MSBM", "MSAM", "Symbol",
                   "EUFM", "EUSM", "RSFS", "LASY", "CMBX", "CMTI", "CMSL")

_LIG = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
    "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "--", "­": "",
}


def normalize_text(s: str) -> str:
    for k, v in _LIG.items():
        s = s.replace(k, v)
    return strip_ctrl(s)


def strip_ctrl(s: str) -> str:
    """Drop C0 control chars (math fonts emit private-use/\\x00 codepoints that
    Postgres text columns reject); keep \\n/\\t."""
    return "".join(c for c in s if c == "\n" or c == "\t" or ord(c) >= 0x20)


# ============================================================================
# in-memory result types (the DB-free replacement for the a_* rows)
# ============================================================================
@dataclass
class ParsedNode:
    """A structural/environment node — the spike's `a_nodes` row, in memory."""

    node_id: str
    parent_id: Optional[str]
    kind: str
    label: Optional[str]
    title: Optional[str]
    heading_path: list[str] = field(default_factory=list)
    page_pdf_start: Optional[int] = None
    page_pdf_end: Optional[int] = None
    page_printed_start: Optional[str] = None
    page_printed_end: Optional[str] = None
    text_raw: Optional[str] = None
    text_normalized: Optional[str] = None
    proves: Optional[str] = None
    math_region_ids: list[str] = field(default_factory=list)
    confidence: Optional[float] = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class ParsedEquation:
    eq_id: str
    pdf_page: int
    bbox: list[float]
    raw_text: str
    latex: Optional[str] = None
    latex_confidence: float = 0.2
    parent_node_id: Optional[str] = None


@dataclass
class RawLine:
    pdf_page: int
    bbox: list[float]
    text: str
    text_orig: str
    font: str
    size: float
    bold: bool
    italic: bool
    is_math: bool
    reading_order: int
    x0: float = 0.0
    math_ratio: float = 0.0


@dataclass
class TocEntry:
    level: int
    raw_label: str
    chapter_number: Optional[int] = None
    section_number: Optional[str] = None
    title: Optional[str] = None
    pdf_page: Optional[int] = None


# ============================================================================
# 1. spans + lines  (track-a/extract.py:extract_spans_and_lines)
# ============================================================================
def _flags(flags: int) -> tuple[bool, bool]:
    return bool(flags & 16), bool(flags & 2)


def _extract_lines(doc: "fitz.Document", page: int) -> list[RawLine]:
    pg = doc[page - 1]
    d = pg.get_text("dict")
    lines: list[RawLine] = []
    lorder = 0
    raw = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            if line["spans"]:
                raw.append(line)
    raw.sort(key=lambda line: (round(line["bbox"][1] / 3), line["bbox"][0]))
    for line in raw:
        sp = line["spans"]
        line_text = "".join(s["text"] for s in sp)
        if not line_text.strip():
            continue
        s0 = sp[0]
        bold0, ital0 = _flags(s0["flags"])

        def _ismf(f: str) -> bool:
            return any(f.startswith(h) or h in f for h in MATH_FONT_HINTS)

        is_math = any(_ismf(s["font"]) for s in sp)
        _tot = sum(len(s["text"]) for s in sp) or 1
        _mch = sum(len(s["text"]) for s in sp if _ismf(s["font"]))
        lines.append(RawLine(
            pdf_page=page, bbox=[round(x, 1) for x in line["bbox"]],
            text=normalize_text(line_text), text_orig=strip_ctrl(line_text),
            font=s0["font"], size=round(s0["size"], 1),
            bold=bold0, italic=ital0, is_math=is_math,
            reading_order=lorder, x0=round(line["bbox"][0], 1),
            math_ratio=round(_mch / _tot, 2),
        ))
        lorder += 1
    return lines


# ============================================================================
# 2. running header / footer + printed-page map (track-a/extract.py)
# ============================================================================
def _page_number_token(toks, page_width: float) -> Optional[str]:
    ints = [(x0, x1, txt) for (x0, x1, _, txt) in toks if re.fullmatch(r"\d{1,3}", txt)]
    if not ints:
        return None
    left = min(ints, key=lambda t: t[0])
    right = max(ints, key=lambda t: t[1])
    if left[0] < 60:
        return left[2]
    if right[1] > page_width - 60:
        return right[2]
    return left[2]


def _detect_headers_footers(doc: "fitz.Document", pages: list[int]) -> dict[int, dict]:
    page_info: dict[int, dict] = {}
    for p in pages:
        pg = doc[p - 1]
        h = pg.rect.height
        w = pg.rect.width
        d = pg.get_text("dict")
        tops, bots = [], []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                for s in line["spans"]:
                    txt = normalize_text(s["text"]).strip()
                    if not txt:
                        continue
                    x0, y0, x1, _ = s["bbox"]
                    if y0 < HEADER_FOOTER_Y_TOP:
                        tops.append((round(x0), round(x1), round(y0, 1), txt))
                    elif y0 > h - HEADER_FOOTER_Y_BOT_MARGIN:
                        bots.append((round(x0), round(x1), round(y0, 1), txt))
        hdr = [t for t in sorted(tops) if t[2] < 35]
        info = {"printed_page": _page_number_token(hdr, w),
                "has_header": bool(hdr)}
        if info["printed_page"] is None and bots:
            info["printed_page"] = _page_number_token(sorted(bots), w)
        page_info[p] = info
    return page_info


def _header_line(line: RawLine) -> bool:
    return line.bbox[1] < HEADER_BAND_Y and line.size < 9.5


def _footer_line(doc: "fitz.Document", line: RawLine) -> bool:
    h = doc[line.pdf_page - 1].rect.height
    return line.bbox[1] > h - HEADER_FOOTER_Y_BOT_MARGIN


# ============================================================================
# 3. heading + environment classification (track-a/extract.py)
# ============================================================================
@dataclass
class _Heading:
    pdf_page: int
    kind: str
    number: str
    title: str
    reading_order: int
    confidence: float
    evidence: list[str]


@dataclass
class _EnvHit:
    pdf_page: int
    reading_order: int
    kind: str
    label: Optional[str]
    number: Optional[str]
    title: Optional[str]
    confidence: float
    evidence: list[str]


def _classify_heading(line: RawLine, in_problems: bool) -> Optional[_Heading]:
    t = line.text.strip()
    m = SECTION_RE.match(t)
    if m and (line.bold or line.size >= SECTION_SIZE_MIN):
        ev = ["matched §N pattern"]
        if line.size >= SECTION_SIZE_MIN:
            ev.append(f"font {line.size}pt >= section threshold")
        if line.bold:
            ev.append("bold")
        return _Heading(line.pdf_page, "section", m.group("num"),
                        normalize_text(m.group("title")).strip(),
                        line.reading_order, 0.95, ev)
    m = CHAPTER_RE.match(t)
    if m and (line.bold or line.size >= CHAPTER_SIZE_MIN):
        return _Heading(line.pdf_page, "chapter", m.group("num"),
                        normalize_text(m.group("title")).strip(),
                        line.reading_order, 0.9,
                        ["matched Chapter K pattern", f"font {line.size}pt"])
    if line.bold and abs(line.size - SUBSECTION_SIZE) < 0.6 and not in_problems:
        if PROBLEMS_RE.match(t):
            return None
        m = SUBSECTION_RE.match(t)
        if m:
            return _Heading(line.pdf_page, "subsection", m.group("num"),
                            m.group("title").strip(), line.reading_order, 0.93,
                            ["matched N.M pattern", "bold 12pt"])
    return None


def _label_hit(line: RawLine, kind: str, t: str, ev: list[str], conf: float) -> _EnvHit:
    lm = LABEL_RE.match(t)
    num = lm.group("num") if lm else None
    title = lm.group("title") if lm else None
    if kind == "proof":
        label = "Proof"
    else:
        label = f"{kind.capitalize()}" + (f" {num}" if num else "")
    return _EnvHit(line.pdf_page, line.reading_order, kind, label, num,
                   (normalize_text(title).strip() if title else None), conf, ev)


def _classify_env(line: RawLine, in_problems: bool) -> Optional[_EnvHit]:
    t = line.text.strip()
    if line.bold and abs(line.size - EXERCISE_SIZE) < 0.6:
        mi = INLINE_EXERCISE_RE.match(t)
        if mi:
            title = (mi.group("title") or "").strip()[:80]
            return _EnvHit(line.pdf_page, line.reading_order, "exercise",
                           f"Exercise {mi.group('num')}", mi.group("num"),
                           title or None, 0.9, ["bold 9pt", "inline Exercise keyword"])
    if (line.bold and abs(line.size - EXERCISE_SIZE) < 0.6
            and in_problems and not FIGURE_RE.match(t)):
        m = EXERCISE_RE.match(t)
        if m:
            return _EnvHit(line.pdf_page, line.reading_order, "exercise",
                           f"Exercise {m.group('num')}", m.group("num"),
                           m.group("title").strip()[:80], 0.9,
                           ["bold 9pt under Problems", "matched N.M. exercise"])
    if line.bold and abs(line.size - ENV_SIZE) < 0.7:
        for kind, rx in ENV_BOLD_10.items():
            if re.match(rx, t):
                return _label_hit(line, kind, t, ["bold 10pt", f"keyword {kind}"], 0.95)
    if line.italic and abs(line.size - ENV_SIZE) < 0.7:
        for kind, rx in ENV_ITALIC_10.items():
            if re.match(rx, t):
                conf = 0.95 if kind == "proof" else 0.93
                return _label_hit(line, kind, t, ["italic 10pt", f"keyword {kind}"], conf)
    return None


# ============================================================================
# 4. outline (TOC)  (track-a/extract.py:parse_outline)
# ============================================================================
def _parse_outline(doc: "fitz.Document") -> list[TocEntry]:
    entries: list[TocEntry] = []
    try:
        toc = doc.get_toc(simple=False)
    except Exception:
        toc = []
    for lvl, title, page, *_ in toc:
        t = normalize_text(title.replace("\r", " ").replace("\\r", " ")).strip()
        chapter_no = section_no = None
        clean_title = t
        if lvl == 1:
            m = CHAPTER_RE.match(t)
            if m:
                chapter_no = int(m.group("num"))
                clean_title = m.group("title").strip()
        elif lvl == 2:
            m = SECTION_RE.match(t)
            if m:
                section_no = m.group("num")
                clean_title = m.group("title").strip()
        elif lvl == 3:
            m = SUBSECTION_RE.match(t)
            if m:
                section_no = m.group("num")
                clean_title = m.group("title").strip()
        entries.append(TocEntry(
            level=lvl, raw_label=t, chapter_number=chapter_no,
            section_number=section_no, title=clean_title, pdf_page=page))
    return entries


def _chapter_for_section(outline: list[TocEntry], section_num: str) -> Optional[str]:
    cur_ch = None
    for e in outline:
        if e.level == 1 and e.chapter_number is not None:
            cur_ch = e.chapter_number
        elif e.level == 2 and e.section_number == section_num:
            return f"book.ch{cur_ch}" if cur_ch else None
    return None


def _chapter_title(outline: list[TocEntry], chapter_node_id: Optional[str]) -> Optional[str]:
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


# ============================================================================
# 5. node assembly — hierarchy + environments + linkage
#    (track-a/extract.py:build_nodes, verbatim logic; DB writes removed)
# ============================================================================
THM_LIKE = {"theorem", "proposition", "lemma", "corollary", "definition"}


def _printed(page_info, p) -> Optional[str]:
    return page_info.get(p, {}).get("printed_page")


def _build_nodes(
    doc: "fitz.Document", pages: list[int], page_info: dict, outline: list[TocEntry]
) -> tuple[list[ParsedNode], list[ParsedEquation]]:
    seq: list[RawLine] = []
    eqs: list[ParsedEquation] = []
    for p in pages:
        for ln in _extract_lines(doc, p):
            if _header_line(ln) or _footer_line(doc, ln):
                continue
            seq.append(ln)

    in_problems = False
    for ln in seq:
        t = ln.text.strip()
        if SECTION_RE.match(t) and (ln.bold or ln.size >= SECTION_SIZE_MIN):
            in_problems = False
        if CHAPTER_RE.match(t) and (ln.bold or ln.size >= CHAPTER_SIZE_MIN):
            in_problems = False
        ln_in_problems = in_problems
        if PROBLEMS_RE.match(t) and ln.bold and abs(ln.size - SUBSECTION_SIZE) < 0.6:
            in_problems = True
        ln.__dict__["_in_problems"] = ln_in_problems

    nodes: list[ParsedNode] = []
    cur_chapter: Optional[ParsedNode] = None
    cur_section: Optional[ParsedNode] = None
    cur_subsection: Optional[ParsedNode] = None
    cur_env: Optional[ParsedNode] = None
    last_thm_like: Optional[ParsedNode] = None
    eq_counter: collections.Counter = collections.Counter()

    def heading_path() -> list[str]:
        hp = []
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

    for ln in seq:
        t = ln.text.strip()
        ip = ln.__dict__.get("_in_problems", False)

        is_label = ln.bold and ln.size >= ENV_SIZE - 0.5
        frag = ln.is_math and not is_label and len(t) >= 2 and (
            ln.math_ratio >= 0.45 or (ln.x0 >= 90 and ln.math_ratio >= 0.20))
        if frag:
            eq_counter[ln.pdf_page] += 1
            eid = f"eq-p{ln.pdf_page}-{eq_counter[ln.pdf_page]}"
            parent = cur_env or cur_subsection or cur_section
            eqs.append(ParsedEquation(
                eq_id=eid, pdf_page=ln.pdf_page, bbox=ln.bbox,
                raw_text=ln.text_orig[:500], latex=None, latex_confidence=0.2,
                parent_node_id=(parent.node_id if parent else None)))
            if cur_env is not None:
                cur_env.math_region_ids.append(eid)

        h = _classify_heading(ln, ip)
        if h is not None:
            close_env(ln.pdf_page)
            if h.kind == "chapter":
                if not h.title:
                    for e in outline:
                        if e.level == 1 and e.chapter_number == int(h.number):
                            h.title = e.title
                            break
                nid = f"book.ch{h.number}"
                cur_chapter = ParsedNode(
                    node_id=nid, parent_id="book", kind="chapter",
                    label=f"Chapter {h.number}", title=h.title,
                    heading_path=[h.title or f"Chapter {h.number}"],
                    page_pdf_start=h.pdf_page,
                    page_printed_start=_printed(page_info, h.pdf_page),
                    confidence=h.confidence, evidence=h.evidence)
                nodes.append(cur_chapter)
                cur_section = cur_subsection = None
                last_thm_like = None
            elif h.kind == "section":
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
                pid = _chapter_for_section(outline, h.number) or (
                    cur_chapter.node_id if cur_chapter else None)
                ch_title = _chapter_title(outline, pid)
                cur_section = ParsedNode(
                    node_id=nid, parent_id=pid, kind="section",
                    label=h.number, title=title,
                    heading_path=([ch_title] if ch_title else []) + [f"§{h.number} {title}".strip()],
                    page_pdf_start=h.pdf_page,
                    page_printed_start=_printed(page_info, h.pdf_page),
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
                cur_subsection = ParsedNode(
                    node_id=nid, parent_id=pid, kind="subsection",
                    label=h.number, title=title,
                    page_pdf_start=h.pdf_page,
                    page_printed_start=_printed(page_info, h.pdf_page),
                    confidence=h.confidence, evidence=ev)
                cur_subsection.heading_path = heading_path()
                nodes.append(cur_subsection)
                last_thm_like = None
            continue

        e = _classify_env(ln, ip)
        if e is not None:
            close_env(ln.pdf_page)
            parent = cur_subsection or cur_section or cur_chapter
            seqno = len(nodes)
            nid = f"{(parent.node_id if parent else 'book')}.{e.kind}{seqno}"
            node = ParsedNode(
                node_id=nid, parent_id=(parent.node_id if parent else None),
                kind=e.kind, label=e.label, title=e.title,
                heading_path=heading_path(),
                page_pdf_start=e.pdf_page,
                page_printed_start=_printed(page_info, e.pdf_page),
                text_raw=ln.text_orig, text_normalized=t,
                confidence=e.confidence, evidence=e.evidence)
            if e.kind == "proof":
                if last_thm_like is not None:
                    node.proves = last_thm_like.node_id
                    node.evidence.append(
                        f"attached to preceding {last_thm_like.kind} {last_thm_like.label}")
                else:
                    node.confidence = min(node.confidence or 1.0, 0.6)
                    node.evidence.append("no preceding theorem-like item to attach")
            nodes.append(node)
            cur_env = node
            if e.kind in THM_LIKE:
                last_thm_like = node
            continue

        if cur_env is not None:
            cur_env.text_raw = (cur_env.text_raw or "") + " " + ln.text_orig
            cur_env.text_normalized = (cur_env.text_normalized or "") + " " + t
            cur_env.page_pdf_end = ln.pdf_page
            cur_env.page_printed_end = _printed(page_info, ln.pdf_page)

    close_env(pages[-1])

    # synthesize chapter nodes referenced by an in-slice section whose opener
    # page is outside the parsed range (e.g. §7 -> Chapter 2). (spike build_nodes)
    have = {n.node_id for n in nodes}
    needed = {n.parent_id for n in nodes if n.kind == "section" and n.parent_id}
    for cid in sorted(needed - have):
        path_title = _chapter_title(outline, cid)
        opener = bare = None
        for e in outline:
            if e.level == 1 and f"book.ch{e.chapter_number}" == cid:
                opener, bare = e.pdf_page, e.title
                break
        nodes.insert(0, ParsedNode(
            node_id=cid, parent_id="book", kind="chapter",
            label=cid.replace("book.ch", "Chapter "), title=bare,
            heading_path=[path_title] if path_title else [],
            page_pdf_start=opener, confidence=0.85,
            evidence=["synthesized from outline (opener outside range)"]))

    _close_hierarchy_spans(nodes, pages[-1], page_info)
    return nodes, eqs


def _close_hierarchy_spans(nodes, last_page, page_info):
    structural = [n for n in nodes if n.kind in ("chapter", "section", "subsection")]
    order = {"chapter": 0, "section": 1, "subsection": 2}
    for i, n in enumerate(structural):
        end = last_page
        for m in structural[i + 1:]:
            if order[m.kind] <= order[n.kind]:
                end = (max(n.page_pdf_start, m.page_pdf_start - 1)
                       if (m.page_pdf_start or 0) > (n.page_pdf_start or 0)
                       else m.page_pdf_start)
                break
        n.page_pdf_end = end
        n.page_printed_end = _printed(page_info, end)


# ============================================================================
# public entry point
# ============================================================================
def parse_pdf(
    pdf_bytes: bytes, page_range: Optional[tuple[int, int]] = None
) -> tuple[list[ParsedNode], list[ParsedEquation]]:
    """Deterministically parse a book PDF into a typed skeleton.

    `pdf_bytes` is the raw PDF (the caller downloads it off the storage plane via
    the platform session). `page_range` is an inclusive 1-based window; `None`
    parses the whole document. Returns `(nodes, equations)` — plain dataclasses
    the workflow maps into `BookNode`s (stamping `book_id` into the ids).

    Ported from `spike/extraction-skeleton:track-a/extract.py:main` minus the DB
    persistence and Tu slice hardcoding.
    """
    import fitz  # lazy — PyMuPDF is an execution-only dep

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_range is not None:
            lo, hi = page_range
            pages = list(range(max(1, lo), min(doc.page_count, hi) + 1))
        else:
            pages = list(range(1, doc.page_count + 1))
        if not pages:
            return [], []
        outline = _parse_outline(doc)
        page_info = _detect_headers_footers(doc, pages)
        nodes, eqs = _build_nodes(doc, pages, page_info, outline)
        return nodes, eqs
    finally:
        doc.close()

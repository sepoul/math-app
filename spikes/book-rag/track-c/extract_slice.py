"""Track C — minimal structured corpus over the shared slice.

DEGRADE-GRACEFULLY SOURCE: Track A's `a_nodes` is the preferred source for
structured index units. When it is empty (R1 reality), we build a self-contained
*minimal* corpus by a direct PyMuPDF (fitz) extract of the slice, leaning on the
same regexes the spec (§8) prescribes. This is scrappy on purpose — it exists so
Track C can stand up the retrieval substrate without blocking on A. When A lands,
`build_index.py --source a_nodes` swaps in behind the same `Node`-shaped rows.

The slice (per issue #57 / _shared.db.SLICE), in *PDF page* numbers:
  Ch1 §1  Smooth Functions on a Euclidean Space   pdf 22-28
  Ch1 §2  Tangent Vectors in R^n as Derivations   pdf 29-36
  Ch1 §3  The Exterior Algebra of Multicovectors  pdf 37-52
  Ch1 §7  Quotients                               pdf 90-104
(Tu numbers sections globally §1..§29; "§7 Quotients" sits in Chapter 1. The
issue's "Ch7 §7" is the spec's section number, not chapter 7 — see TOC.)

Output: a list of `_shared.schema.Node`-shaped dicts (section + leaf nodes), each
carrying page mapping and raw text. Equations are NOT separately minted here
(that is Track A/§9); we keep raw glyph text inline as evidence.
"""
from __future__ import annotations

import re
import sys
import pathlib
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import ensure_book, SLICE  # noqa: E402

import fitz  # PyMuPDF


def clean_text(s: str) -> str:
    """Strip NUL/control bytes that Postgres text columns reject. Math-font PDFs
    emit stray \\x00 and other C0 controls in glyph-soup regions."""
    if not s:
        return s
    return "".join(ch for ch in s if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)


# ---- the slice, as (section_number, title, chapter_title, pdf_start, pdf_end) --
# pdf_end is inclusive; ranges come straight from the embedded outline (TOC).
CHAPTER1 = "Chapter 1: Euclidean Spaces"
SLICE_SECTIONS = [
    ("1", "Smooth Functions on a Euclidean Space", CHAPTER1, 22, 28),
    ("2", "Tangent Vectors in Rn as Derivations", CHAPTER1, 29, 36),
    ("3", "The Exterior Algebra of Multicovectors", CHAPTER1, 37, 52),
    ("7", "Quotients", CHAPTER1, 90, 104),
]
BOOK_TITLE = "An Introduction to Manifolds"

# ---- spec §8 environment patterns (re-tuned for Tu) ---------------------------
# Tu labels: "Definition 1.1", "Theorem 2.2", "Example 3.4", "Exercise 3.6 (..)*",
# bare "Remark", "Example", "Proof." — the number may be absent.
ENV_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("definition",  re.compile(r"^(Definition)s?\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("theorem",     re.compile(r"^(Theorem)\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("proposition", re.compile(r"^(Proposition)\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("lemma",       re.compile(r"^(Lemma)\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("corollary",   re.compile(r"^(Corollary)\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("example",     re.compile(r"^(Example)\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("remark",      re.compile(r"^(Remark)\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("exercise",    re.compile(r"^(Exercise|Problem)\b\.?\s*(\d+(?:\.\d+)*)?", re.I)),
    ("proof",       re.compile(r"^(Proof)\b\.?", re.I)),
]
# subsection heading like "1.1 C∞ Versus Analytic Functions" or "7.1 The Quotient Topology"
SUBSEC = re.compile(r"^(\d+)\.(\d+)\s+([A-Z].+)$")
# a section running-header / heading: "§7 Quotients"
SECTION_HDR = re.compile(r"^§\s*(\d+)\b")
# a parenthetical title right after the label: "Lemma 1.4 (Taylor's theorem ...)"
TITLE_PAREN = re.compile(r"^[A-Za-z]+\s*[\d.]*\s*\(([^)]+)\)")


@dataclass
class Leaf:
    kind: str
    label: str | None
    title: str | None
    pdf_page: int          # page where the label starts
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def _printed_page_for(pdf_page: int) -> str:
    """Tu front matter ≈ +19 offset across the slice (printed = pdf - 19)."""
    return str(pdf_page - 19)


def _strip_running_furniture(page_lines: list[str], sec_title: str) -> list[str]:
    """Drop the running header (section title) and the bare page-number line that
    appear at the top of every body page. Conservative: only the first 1-2 lines."""
    out = list(page_lines)
    # the section title appears as a running header (often duplicated); drop leading
    # copies of it and any standalone all-digit line in the first two positions.
    for _ in range(2):
        if not out:
            break
        head = out[0].strip()
        if head.isdigit():
            out = out[1:]
            continue
        if sec_title and head and (head in sec_title or sec_title in head):
            out = out[1:]
            continue
        if SECTION_HDR.match(head):
            out = out[1:]
            continue
        break
    return out


def extract_section(doc, sec_num: str, title: str, chapter: str,
                    pdf_start: int, pdf_end: int) -> tuple[dict, list[dict]]:
    """Return (section_node_dict, [leaf_node_dict, ...]) for one slice section."""
    heading_path = [BOOK_TITLE, chapter, f"§{sec_num} {title}"]
    sec_node_id = f"c.tu.sec{sec_num}"

    # 1) flatten the section to a stream of (pdf_page, line), stripping furniture
    stream: list[tuple[int, str]] = []
    section_all_text: list[str] = []
    for pidx in range(pdf_start - 1, pdf_end):  # pdf_start is 1-indexed
        page_lines = clean_text(doc[pidx].get_text("text")).splitlines()
        page_lines = _strip_running_furniture(page_lines, f"§{sec_num} {title}")
        for ln in page_lines:
            s = ln.rstrip()
            # drop the bare "§N ..." real heading line on the section's first page
            if pidx == pdf_start - 1 and SECTION_HDR.match(s.strip()):
                continue
            stream.append((pidx + 1, s))
            section_all_text.append(s)

    # 2) walk the stream, opening a new leaf whenever a label line appears
    leaves: list[Leaf] = []
    cur: Leaf | None = None
    for pdf_page, line in stream:
        s = line.strip()
        matched_kind = None
        matched_label = None
        for kind, pat in ENV_PATTERNS:
            m = pat.match(s)
            if m:
                # guard against mid-sentence refs like "(see Problem 7.2)" that wrap
                # to a line start: a real label isn't immediately followed by ")".
                if s[m.end():].lstrip().startswith(")"):
                    continue
                matched_kind = kind
                if kind == "proof":
                    matched_label = None
                else:
                    num = m.group(2) if (m.lastindex and m.lastindex >= 2) else None
                    matched_label = (f"{m.group(1).capitalize()} {num}".strip()
                                     if num else m.group(1).capitalize())
                break
        is_subsec = bool(SUBSEC.match(s))
        if matched_kind:
            title_m = TITLE_PAREN.match(s)
            leaf_title = title_m.group(1).strip() if title_m else None
            cur = Leaf(kind=matched_kind, label=matched_label, title=leaf_title,
                       pdf_page=pdf_page, lines=[s])
            leaves.append(cur)
        elif is_subsec:
            cur = None  # exposition between labels; folded into section text only
        elif cur is not None:
            cur.lines.append(line)

    # 3) build dicts
    sec_text = "\n".join(section_all_text).strip()
    sec_dict = dict(
        node_id=sec_node_id, parent_id=None, kind="section",
        label=f"§{sec_num}", title=title, heading_path=heading_path,
        page_pdf_start=pdf_start, page_pdf_end=pdf_end,
        page_printed_start=_printed_page_for(pdf_start),
        page_printed_end=_printed_page_for(pdf_end),
        text_raw=sec_text, proves=None, confidence=0.9,
    )

    leaf_dicts: list[dict] = []
    THM_LIKE = {"theorem", "proposition", "lemma", "corollary"}
    prev_thm_id: str | None = None
    counters: dict[str, int] = {}
    for lf in leaves:
        counters[lf.kind] = counters.get(lf.kind, 0) + 1
        # always include an ordinal so bare/duplicate labels (two "Example"s) are
        # unique; append the label when present for readability.
        base = lf.label.replace(" ", "_").replace(".", "_") if lf.label else lf.kind
        suffix = f"{base}_{counters[lf.kind]}"
        nid = f"c.tu.sec{sec_num}.{lf.kind}.{suffix}".lower()
        proves = prev_thm_id if (lf.kind == "proof" and prev_thm_id) else None
        leaf_dicts.append(dict(
            node_id=nid, parent_id=sec_node_id, kind=lf.kind,
            label=lf.label, title=lf.title, heading_path=heading_path,
            page_pdf_start=lf.pdf_page, page_pdf_end=lf.pdf_page,
            page_printed_start=_printed_page_for(lf.pdf_page),
            page_printed_end=_printed_page_for(lf.pdf_page),
            text_raw=lf.text, proves=proves, confidence=0.85,
        ))
        if lf.kind in THM_LIKE:
            prev_thm_id = nid
    return sec_dict, leaf_dicts


def extract_slice() -> tuple[list[dict], list[dict]]:
    """Return (section_nodes, leaf_nodes) for the whole shared slice."""
    doc = fitz.open(ensure_book())
    sections: list[dict] = []
    leaves: list[dict] = []
    for sec_num, title, chapter, p0, p1 in SLICE_SECTIONS:
        sec, lvs = extract_section(doc, sec_num, title, chapter, p0, p1)
        sections.append(sec)
        leaves.extend(lvs)
    return sections, leaves


if __name__ == "__main__":
    secs, leaves = extract_slice()
    print(f"slice = {SLICE}")
    print(f"section nodes: {len(secs)}  leaf nodes: {len(leaves)}")
    from collections import Counter
    print("leaf kinds:", dict(Counter(l["kind"] for l in leaves)))
    for s in secs:
        n = sum(1 for l in leaves if l["parent_id"] == s["node_id"])
        print(f"  {s['label']} {s['title']!r}  pdf {s['page_pdf_start']}-{s['page_pdf_end']}  ({n} leaves)")

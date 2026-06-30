"""Tu-specific parser configuration — the *corrected* config for
L. W. Tu, *An Introduction to Manifolds* (2nd ed.).

This is the central learning of Track A round 1: the spec's generic
heading/environment regexes mis-fire on Tu. Tu's structure is:

  * Chapters   : ``Chapter K: Title`` (a leading L1 outline entry; the in-body
                 opener renders ``Chapter K`` in Times-Bold ~14.3pt).
  * Sections   : ``§N Title``  (CONTINUOUS book-wide numbering, NOT per chapter;
                 e.g. §7 Quotients lives *inside Chapter 2*, not "Chapter 7").
                 In-body the ``§`` + ``N`` render Times-Bold ~14.3pt.
  * Subsections: ``N.M Title`` (Times-Bold ~12pt). N tracks the *section*
                 number, not the chapter.
  * Exercises  : live under a ``Problems`` block (Times-Bold 12pt header),
                 each exercise labelled ``N.M.`` (Times-Bold 9pt) with a short
                 title; ``*`` marks harder problems.

Formal environments are reliably separable by TYPOGRAPHY, not regex alone:

  | env                                   | font         | size | sample          |
  |---------------------------------------|--------------|------|-----------------|
  | definition                            | Times-Bold   | 10   | "Definition 1.1."|
  | theorem/proposition/lemma/corollary   | Times-Bold   | 10   | "Theorem 7.9."  |
  | proof                                 | Times-Italic | 10   | "Proof."        |
  | example/remark                        | Times-Italic | 10   | "Example 1.2."  |
  | exercise (in Problems)                | Times-Bold   | 9    | "1.1. A ..."    |

Body text is Times-Roman 10pt. Math glyph-soup arrives in CM*/MSBM/Symbol
fonts (CMR10, CMSY10, CMMI10, MSBM10, Symbol, ...).

Page mapping: the printed page number lives in the running header (top
margin, y~=27.7). Offset PDF->printed is ~19 in the slice but is NOT assumed
constant — it is read per page from the header. Front matter pushes it.
"""
from __future__ import annotations

import re

# ---- typography thresholds (points) --------------------------------------
BODY_FONT = "Times-Roman"
BODY_SIZE = 10.0

CHAPTER_SIZE_MIN = 13.5          # Times-Bold ~14.3
SECTION_SIZE_MIN = 13.5          # §N renders at the same ~14.3 bold size
SUBSECTION_SIZE = 12.0           # Times-Bold 12 (also "Problems" header -> disambiguate by text)
ENV_SIZE = 10.0                  # bold-10 (def/thm/...) and italic-10 (proof/example/remark)
EXERCISE_SIZE = 9.0              # bold-9 inside Problems (also figure captions -> disambiguate)

# The running header sits at a stable y~=27.7; the FIRST body line can be as
# high as y~=47 (a theorem label opening a page). So the header band must be
# TIGHT (y<35) or it eats body labels. A wider scan band (y<60) is used only
# to *collect* header candidates, then the size<9.5 guard + stable-y separate
# them from body. See FINDINGS "header band" risk.
HEADER_FOOTER_Y_TOP = 60.0          # collection band for header candidates
HEADER_BAND_Y = 35.0                # the running header's actual stable-y ceiling
HEADER_FOOTER_Y_BOT_MARGIN = 45.0   # footer band (page number ~ bottom margin)

# ---- environment vocabulary ----------------------------------------------
# fi/fl ligatures are normalized away before matching (see normalize_text).
ENV_BOLD_10 = {       # Times-Bold 10pt label lines
    "definition": r"^Definition\b",
    "theorem": r"^Theorem\b",
    "proposition": r"^Proposition\b",
    "lemma": r"^Lemma\b",
    "corollary": r"^Corollary\b",
}
ENV_ITALIC_10 = {     # Times-Italic 10pt label lines
    "proof": r"^Proof\b",
    "example": r"^Example\b",
    "remark": r"^Remark\b",
}

# label like "Theorem 7.9", "Definition 1.1", "Example 3.3", optional "(Title)"
LABEL_RE = re.compile(
    r"^(?P<kw>Definition|Theorem|Proposition|Lemma|Corollary|Example|Remark|Exercise)"
    r"(?:\s+(?P<num>\d+(?:\.\d+)*)\*?)?"
    r"(?:\s*\((?P<title>[^)]*)\))?"
)

# in-Problems exercise:  "1.1." / "1.2.* A C-infinity function ..."
EXERCISE_RE = re.compile(r"^(?P<num>\d+\.\d+)\.(?P<star>\*)?\s+(?P<title>.+)$")

# figure caption to EXCLUDE from exercise/bold-9 detection
FIGURE_RE = re.compile(r"^Fig(?:ure)?\.?\s", re.IGNORECASE)

# Tu section heading in-body: "§N Title" (the section glyph may be a separate span)
SECTION_RE = re.compile(r"^§\s*(?P<num>\d+)\b\s*(?P<title>.*)$")
# chapter opener: "Chapter K" (title is on the L1 outline / next line)
CHAPTER_RE = re.compile(r"^Chapter\s+(?P<num>\d+)\b\s*:?\s*(?P<title>.*)$")
# subsection: "N.M Title" (title must start non-digit so we don't grab equations)
SUBSECTION_RE = re.compile(r"^(?P<num>\d+\.\d+)\s+(?P<title>\D.*)$")

PROBLEMS_RE = re.compile(r"^Problems\s*$")

# math-glyph font families (the "glyph-soup" producers)
MATH_FONT_HINTS = ("CMR", "CMMI", "CMSY", "CMEX", "MSBM", "MSAM", "Symbol",
                   "EUFM", "EUSM", "RSFS", "LASY", "CMBX", "CMTI", "CMSL")

# ---- normalization -------------------------------------------------------
_LIG = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
    "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
    "’": "'", "‘": "'", "“": '"', "”": '"',
    "–": "-", "—": "--", "­": "",
}


def normalize_text(s: str) -> str:
    for k, v in _LIG.items():
        s = s.replace(k, v)
    return strip_ctrl(s)


def strip_ctrl(s: str) -> str:
    """Remove NUL + other C0 control chars (math fonts emit \\x00/\\x12/\\x13
    private-use codepoints that PostgreSQL text columns reject). Keep \\n/\\t."""
    return "".join(c for c in s if c == "\n" or c == "\t" or ord(c) >= 0x20)

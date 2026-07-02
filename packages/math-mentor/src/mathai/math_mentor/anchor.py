"""The GroundedAnchor resolver (issue #68) — the seam onto `book_retrieve`.

`resolve_anchor` turns a request to locate a spot in a book into a
source-traceable `GroundedAnchor` carrying an **honest trust level**. It reads
book knowledge through *exactly one* interface — the `BookRetrieveFn` port (see
`port.py`) — called exactly once. No SQL, no OCR, no regex over book text, no
vector store, no filesystem/DB access: every byte of book knowledge flows
through that one port call.

    deploy wiring is DEFERRED — this module is the resolver LOGIC contract only.
    There is intentionally no bundle.toml / control.py / execution.py yet;
    turning math_mentor into a deployable platform job is future work
    (#69/#70/#71).

Trust levels (see `GroundedAnchor.trust_level`):

  * ``grounded``          — a returned hit's label matched the requested
                            coordinate exactly; we copy that hit's traceability
                            fields verbatim.
  * ``section-grounded``  — no coordinate match, but the best topical hit clears
                            the score floor; we ground to its *section*
                            (heading_path / page / source) with ``label=None``
                            and ``node_id=None`` — no false precision.
  * ``ungrounded``        — no usable hit (empty result, or nothing above the
                            floor); every traceability field is empty.

``matched == (trust_level != "ungrounded")``.

The resolver **never fabricates**: ``label`` / ``node_id`` are only ever copied
from a hit the retriever returned. A coordinate with no matching label yields at
most ``section-grounded`` (``label=None``), never a confident wrong label.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from mathai.math_book.models import (
    BookRetrievalResult,
    BookRetrieveInput,
    RetrievalIntent,
)

from mathai.math_mentor.port import BookRetrieveFn

# --- tunables (provisional; #55 calibrates the real numbers) ------------------

#: Number of ranked hits to ask `book_retrieve` for. Matches the
#: `BookRetrieveInput` default; exposed as a constant so callers/tests can see
#: (and #55 can tune) the retrieval width in one place.
DEFAULT_K = 8

#: Minimum hit score for a *topical* (non-coordinate) match to be trusted as
#: ``section-grounded``. Below it, we return ``ungrounded`` rather than ground
#: to noise. Provisional default — the score scale (cosine vs post-rerank) and
#: the calibrated floor are settled by #55. An exact coordinate-label match is
#: NOT gated by this floor: an explicit label match is the strongest possible
#: signal and grounds regardless of score.
DEFAULT_SCORE_FLOOR = 0.35


# --- the contract model -------------------------------------------------------


TrustLevel = Literal["grounded", "section-grounded", "ungrounded"]


class GroundedAnchor(BaseModel):
    """A source-traceable pointer into a book, with an honest trust level.

    Field set is the authoritative #68 contract — do not add/rename fields.

    Invariant enforced by `resolve_anchor`:
    ``matched == (trust_level != "ungrounded")``. `label`/`node_id` are only ever
    populated by copying a returned hit — never synthesized.
    """

    model_config = ConfigDict(extra="forbid")

    book_id: str = Field(..., description="The book this anchor points into (namespacing).")
    node_id: Optional[str] = Field(
        None, description="Structural node id — copied from a hit ONLY on a coordinate match."
    )
    label: Optional[str] = Field(
        None, description="Citation label (e.g. 'Problem 2.16') — copied from a hit ONLY on a coordinate match."
    )
    page: Optional[int] = Field(None, description="1-based source page, if the grounding hit carried one.")
    heading_path: list[str] = Field(
        default_factory=list, description="Breadcrumb from the book root (grounding hit's section)."
    )
    source: Optional[str] = Field(
        None, description="Pre-rendered human-readable citation from the grounding hit."
    )
    score: Optional[float] = Field(None, description="Score of the grounding hit, if any.")
    query: str = Field(..., description="The query used for retrieval (coordinate if given, else topic).")
    trust_level: TrustLevel = Field(
        ..., description="grounded | section-grounded | ungrounded — how much to trust this anchor."
    )
    matched: bool = Field(
        ..., description="True iff trust_level != 'ungrounded' (something usable was found)."
    )


# --- coordinate normalization -------------------------------------------------

# Canonical form for the leading "kind" word of a coordinate, so variant
# spellings/abbreviations compare equal. A coordinate matches a hit's label iff
# their normalized forms are identical, so BOTH sides pass through this map.
_KIND_ALIASES: dict[str, str] = {
    "problem": "problem", "problems": "problem", "prob": "problem", "prb": "problem", "pb": "problem",
    "exercise": "exercise", "exercises": "exercise", "exer": "exercise", "exc": "exercise", "ex": "exercise",
    "section": "section", "sections": "section", "sect": "section", "sec": "section",
    "chapter": "chapter", "chapters": "chapter", "chap": "chapter", "ch": "chapter",
    "part": "part",
    "theorem": "theorem", "theorems": "theorem", "thm": "theorem",
    "lemma": "lemma", "lemmas": "lemma", "lem": "lemma",
    "proposition": "proposition", "propositions": "proposition", "prop": "proposition",
    "corollary": "corollary", "corollaries": "corollary", "cor": "corollary",
    "definition": "definition", "definitions": "definition", "defn": "definition", "def": "definition",
    "example": "example", "examples": "example", "exmp": "example", "eg": "example",
    "remark": "remark", "remarks": "remark", "rmk": "remark", "rem": "remark",
    "figure": "figure", "figures": "figure", "fig": "figure",
    "equation": "equation", "equations": "equation", "eqn": "equation", "eq": "equation",
    "table": "table", "tbl": "table",
}

# A coordinate number: one or more dotted/hyphenated integer groups, e.g.
# "2.16", "21.4", "1.2.4", "21-4". Hyphens are normalized to dots.
_NUMBER_RE = re.compile(r"\d+(?:[.\-]\d+)*")
# The leading alphabetic "kind" token.
_KIND_RE = re.compile(r"[a-z]+")


def normalize_coordinate(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a coordinate/label so variant spellings compare equal.

    Unifies case, whitespace, the ``§`` section marker, abbreviations, and
    hyphen-vs-dot number separators, into a ``"<kind> <number>"`` form
    (either part may be absent). A coordinate is a match for a hit iff
    ``normalize_coordinate(coordinate) == normalize_coordinate(hit.label)``.

    Examples (all resolve to a shared canonical form):
        "Problem 2.16"          -> "problem 2.16"
        "§21.4" / "Section 21.4"-> "section 21.4"
        "Ex 1.2.4" / "Exercise 1.2.4" -> "exercise 1.2.4"
        "  §21-4 "              -> "section 21.4"

    Returns ``None`` for ``None``/empty/garbage input (a ``None`` never equals a
    real normalized coordinate, so a hit with ``label=None`` can never match).
    """
    if raw is None:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    # § is a section marker (bare or glued to the number, e.g. "§21.4").
    s = s.replace("§", " section ")

    number_match = _NUMBER_RE.search(s)
    number = number_match.group(0).replace("-", ".") if number_match else None

    kind_match = _KIND_RE.search(s)
    kind: Optional[str] = None
    if kind_match:
        raw_kind = kind_match.group(0)
        kind = _KIND_ALIASES.get(raw_kind, raw_kind)

    parts = [p for p in (kind, number) if p]
    return " ".join(parts) if parts else None


# --- the resolver -------------------------------------------------------------


def resolve_anchor(
    retrieve: BookRetrieveFn,
    book_id: str,
    coordinate: Optional[str],
    topic: str,
    intent: Optional[RetrievalIntent] = None,
    *,
    k: int = DEFAULT_K,
    score_floor: float = DEFAULT_SCORE_FLOOR,
) -> GroundedAnchor:
    """Resolve a (book, coordinate, topic) request to a `GroundedAnchor`.

    `retrieve` is the ONLY source of data — the `book_retrieve` port, called
    exactly once. `book_id` flows straight into the retrieval input, so
    retrieval is book-scoped at the call site (a Tu query can't return Hatcher).

    Logic (see module docstring for the trust-level definitions):

      1. **Coordinate-first.** ``query = coordinate if coordinate else topic``.
         Ask the port once. If a coordinate was given and some hit's normalized
         label equals the normalized coordinate → ``grounded``: copy that hit's
         ``node_id`` / ``label`` / ``page`` / ``heading_path`` / ``source`` /
         ``score`` verbatim. (Not gated by ``score_floor`` — an exact label match
         is the strongest signal.)
      2. **Section fallback.** Else, if the best hit clears ``score_floor`` →
         ``section-grounded``: ground to its *section* (``heading_path`` / ``page``
         / ``source`` / ``score``) with ``label=None`` and ``node_id=None`` (no
         false precision).
      3. **Ungrounded.** Else (empty hits, or nothing above the floor) → every
         traceability field empty, ``matched=False``.

    `intent` is forwarded into the retrieval input to steer the hybrid mix.
    """
    query = coordinate if coordinate else topic

    req = BookRetrieveInput(book_id=book_id, query=query, k=k, intent=intent)
    result: BookRetrievalResult = retrieve(req)
    hits = list(result.hits or [])

    # 1) Coordinate-first exact grounding. Search ALL hits for a label whose
    #    normalized form equals the normalized coordinate; if several match,
    #    take the highest-scoring one. label=None hits never match.
    norm_coord = normalize_coordinate(coordinate)
    if norm_coord is not None:
        label_matches = [
            h for h in hits if normalize_coordinate(h.label) == norm_coord
        ]
        if label_matches:
            best = max(label_matches, key=lambda h: h.score)
            return GroundedAnchor(
                book_id=book_id,
                node_id=best.node_id,
                label=best.label,
                page=best.page,
                heading_path=list(best.heading_path),
                source=best.source,
                score=best.score,
                query=query,
                trust_level="grounded",
                matched=True,
            )

    # 2) Section-grounded fallback: the best topical hit above the floor. The
    #    port already scoped by book_id + query, so a hit clearing the floor is
    #    by construction topically relevant — we ground to its section but NOT
    #    to a coordinate label (label/node_id stay None: no false precision).
    if hits:
        best = max(hits, key=lambda h: h.score)
        if best.score >= score_floor:
            return GroundedAnchor(
                book_id=book_id,
                node_id=None,
                label=None,
                page=best.page,
                heading_path=list(best.heading_path),
                source=best.source,
                score=best.score,
                query=query,
                trust_level="section-grounded",
                matched=True,
            )

    # 3) Ungrounded: nothing usable. Never fabricate.
    return GroundedAnchor(
        book_id=book_id,
        node_id=None,
        label=None,
        page=None,
        heading_path=[],
        source=None,
        score=None,
        query=query,
        trust_level="ungrounded",
        matched=False,
    )

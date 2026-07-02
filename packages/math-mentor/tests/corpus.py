"""The shared 10-note detection corpus (issue #69) — a REUSABLE fixture module.

`#70` (arbitration) and `#71` import this module, so it is authored as a shared
fixture, not inline in one test file. It supplies, for the dates
``2025-06-19 .. 2025-06-28``:

  * `build_notes()` — the 10 `NoteView`s.
  * `build_retrieve()` — an in-memory `BookRetrieveFn` seeded with the relevant
    Tu book-skeleton hits, so coordinates resolve ``grounded`` and topical prose
    resolves ``section-grounded`` (and off-book prose stays ``ungrounded``).
  * `build_extractor()` — an in-memory `SignalExtractor` seeded with the
    verbatim quotes / dispositions / concept mentions the LLM step *would* have
    produced (the corpus owns the extractor's "expected outputs").
  * `build_corpus()` — all three bundled, plus the book id.

The fixture realizes every acceptance-criteria scenario:

  =========  ==================================================================
  date       scenario
  =========  ==================================================================
  06-19      determinant-bridge chain: concept ``determinant``
  06-20      determinant-bridge concept ``kernel`` + an unverified_proof (repair)
  06-21      determinant-bridge concept ``SL(m)``
  06-22      determinant-bridge concept ``regular level set``
  06-23      abandoned struggle about an **off-book** trick → no anchor → dropped
  06-24      **light/brief** day, but a real verbal-cue abandoned_crux (fires on
             the transcript cue, not on density)
  06-25      **deliberate in-progress** + ``dont_spoil`` → not a crux
  06-26      **resolved** struggle (heavy effort language, but he cracked it) →
             not a crux; also a ``compactness`` concept mention
  06-27      determinant-bridge concept ``submersion`` — the ripe connecting
             moment (SL(m) = a regular level set of det)
  06-28      canonical abandoned_crux hedge with a **grounded** (coordinate) anchor
  =========  ==================================================================

The determinant appears as five *distinct* concept strings — ``determinant``,
``kernel``, ``SL(m)``, ``regular level set``, ``submersion`` — that **share no
word**, yet all resolve into one Tu skeleton region (``§9 The Regular Level Set
Theorem``). They bridge purely because their **retrieval anchors overlap**, not
by string matching. ``compactness`` recurs on two dates in a *different* region
but is a single concept, so it must NOT bridge.
"""
from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

from mathai.math_book.models import (
    BookRetrievalHit,
    BookRetrievalResult,
    BookRetrieveInput,
)
from mathai.math_mentor.arbitration import NightCue
from mathai.math_mentor.detection import NoteView
from mathai.math_mentor.signals import ConceptMention, ExtractedStruggle

# --- the book + its skeleton regions ------------------------------------------

BOOK_ID = "Tu"  # Tu, "An Introduction to Manifolds"

#: The determinant-bridge region: every bridge concept resolves into this
#: chapter+section, so their anchors share this 2-level heading_path prefix.
REGION_R = ["Chapter 2: Manifolds", "§9 The Regular Level Set Theorem"]
#: A different region (compactness) — used for the same-concept negative control.
REGION_S = ["Chapter 5: Topology of Manifolds", "§27 Compactness"]

# --- dates --------------------------------------------------------------------

D19, D20, D21, D22, D23 = (
    "2025-06-19", "2025-06-20", "2025-06-21", "2025-06-22", "2025-06-23",
)
D24, D25, D26, D27, D28 = (
    "2025-06-24", "2025-06-25", "2025-06-26", "2025-06-27", "2025-06-28",
)
ALL_DATES = [D19, D20, D21, D22, D23, D24, D25, D26, D27, D28]

#: The five distinct concept strings that make up the determinant bridge. They
#: share no common token — literal-overlap clustering could never unite them.
DETERMINANT_CONCEPTS = ["determinant", "kernel", "SL(m)", "regular level set", "submersion"]


# --- fake port ----------------------------------------------------------------


def hit(
    chunk_id: str = "c1",
    *,
    label: Optional[str] = None,
    node_id: Optional[str] = None,
    page: Optional[int] = None,
    heading_path: Optional[list[str]] = None,
    source: Optional[str] = None,
    score: float = 0.9,
    text: str = "chunk body",
) -> BookRetrievalHit:
    """Build a `BookRetrievalHit` (same helper shape as `test_resolve_anchor.py`)."""
    return BookRetrievalHit(
        chunk_id=chunk_id,
        node_id=node_id,
        text=text,
        score=score,
        label=label,
        page=page,
        heading_path=heading_path or [],
        source=source,
    )


class _Rule(NamedTuple):
    keywords: tuple[str, ...]  # any keyword as a substring of the (lowered) query matches
    hits: tuple[BookRetrievalHit, ...]


class SeededBookRetrieve:
    """An in-memory `BookRetrieveFn` seeded with keyword→hits rules.

    First rule whose keyword is a substring of the (lower-cased) query wins; if
    none match, the query is *off-book* and an empty result is returned (so
    `resolve_anchor` yields ``ungrounded``). Records every request for seam
    assertions, exactly like the #68 fake.
    """

    def __init__(self, rules: Sequence[_Rule]) -> None:
        self._rules = list(rules)
        self.calls: list[BookRetrieveInput] = []

    def __call__(self, req: BookRetrieveInput) -> BookRetrievalResult:
        self.calls.append(req)
        q = (req.query or "").lower()
        for rule in self._rules:
            if any(kw in q for kw in rule.keywords):
                return BookRetrievalResult(
                    book_id=req.book_id, query=req.query, hits=list(rule.hits)
                )
        return BookRetrievalResult(book_id=req.book_id, query=req.query, hits=[])


def _region_hit(node_id: str, subsection: str, region: list[str], page: int, score: float) -> BookRetrievalHit:
    path = [*region, subsection]
    return hit(
        node_id=node_id,
        heading_path=path,
        page=page,
        source=" › ".join(path) + f" (p.{page})",
        score=score,
    )


def build_retrieve() -> SeededBookRetrieve:
    """The seeded fake `book_retrieve` port for the corpus."""
    rules: list[_Rule] = [
        # --- coordinate-first (grounded) -------------------------------------
        # 06-28's crux names Problem 11.1 → an exact label match grounds it.
        _Rule(
            ("problem 11.1",),
            (
                hit(
                    "tu-11-p1",
                    label="Problem 11.1",
                    node_id="tu-11-p1",
                    page=142,
                    heading_path=["Chapter 4: Integration", "§11 Stokes' Theorem"],
                    source="Chapter 4: Integration › §11 Stokes' Theorem › Problem 11.1 (p.142)",
                    score=0.71,
                ),
            ),
        ),
        # --- determinant-bridge region R (topical → section-grounded) --------
        _Rule(("determinant",), (_region_hit("tu-9-det", "The determinant as a smooth map", REGION_R, 98, 0.66),)),
        _Rule(("kernel",), (_region_hit("tu-9-ker", "Rank and kernel", REGION_R, 99, 0.63),)),
        _Rule(
            ("sl(m)", "special linear"),
            (_region_hit("tu-9-sln", "Example: SL(n) as a regular level set", REGION_R, 101, 0.68),),
        ),
        _Rule(("regular level set",), (_region_hit("tu-9-rls", "The regular level set theorem", REGION_R, 100, 0.70),)),
        _Rule(
            ("submersion", "regular value"),
            (_region_hit("tu-9-rvt", "Regular values and submersions", REGION_R, 100, 0.69),),
        ),
        # --- compactness region S (negative control) -------------------------
        _Rule(("compactness", "compact"), (_region_hit("tu-27-cpt", "Compact manifolds", REGION_S, 250, 0.64),)),
        # --- repair-signal topical anchors -----------------------------------
        _Rule(
            ("diagonaliz",),
            (_region_hit("tu-3-diag", "Symmetric matrices", ["Chapter 1: Euclidean Spaces", "§3 Linear Algebra Review"], 20, 0.58),),
        ),
        _Rule(
            ("inverse function theorem",),
            (_region_hit("tu-8-ift", "Statement and proof", ["Chapter 2: Manifolds", "§8 The Inverse Function Theorem"], 90, 0.60),),
        ),
        _Rule(
            ("stokes",),  # topical fallback if a query ever uses the topic instead of the coordinate
            (_region_hit("tu-11-stokes", "Stokes' theorem", ["Chapter 4: Integration", "§11 Stokes' Theorem"], 140, 0.62),),
        ),
        # NB: 06-23's "a Fourier convergence trick from a video" matches nothing
        # → empty result → ungrounded (the AC4 drop).
    ]
    return SeededBookRetrieve(rules)


# --- fake extractor -----------------------------------------------------------


class FakeSignalExtractor:
    """An in-memory `SignalExtractor` seeded with per-date expected outputs.

    Holds what the LLM step *would* have returned for each note — verbatim
    quotes, resolution dispositions, concept mentions — so the deterministic
    detection policy can be exercised with no model call. Reusable: `#70`/`#71`
    (and ad-hoc tests) can build their own with different seeds.
    """

    def __init__(
        self,
        struggles: dict[str, list[ExtractedStruggle]],
        mentions: dict[str, list[ConceptMention]],
    ) -> None:
        self._struggles = struggles
        self._mentions = mentions

    def extract_struggles(self, note: NoteView) -> list[ExtractedStruggle]:
        return list(self._struggles.get(note.date, []))

    def extract_concept_mentions(self, note: NoteView) -> list[ConceptMention]:
        return list(self._mentions.get(note.date, []))


def build_extractor() -> FakeSignalExtractor:
    """The seeded fake extractor for the corpus."""
    struggles: dict[str, list[ExtractedStruggle]] = {
        # 06-20: an unverified proof he didn't check (repair → survives, section-grounded).
        D20: [
            ExtractedStruggle(
                kind="unverified_proof",
                verbatim_quote="I think I proved the inverse function theorem case, but honestly I'm not sure the estimate is tight — moving on.",
                topic="the inverse function theorem",
                written_coordinate=None,
                disposition="abandoned",
            )
        ],
        # 06-23: abandoned, real quote — but the topic is OFF-BOOK → ungrounded → dropped (AC4).
        D23: [
            ExtractedStruggle(
                kind="abandoned_crux",
                verbatim_quote="I just used that Fourier convergence trick from that video, not going to prove it, moving on.",
                topic="a Fourier convergence trick from a video",
                written_coordinate=None,
                disposition="abandoned",
            )
        ],
        # 06-24: light day, but a real verbal-cue crux (fires on the transcript cue, not density).
        D24: [
            ExtractedStruggle(
                kind="abandoned_crux",
                verbatim_quote="Eh, I'll just assume I can diagonalize it and keep going.",
                topic="diagonalizing a symmetric matrix",
                written_coordinate=None,
                disposition="abandoned",
            )
        ],
        # 06-25: deliberate in-progress — NOT abandoned → dropped (resolution clause).
        D25: [
            ExtractedStruggle(
                kind="abandoned_crux",
                verbatim_quote="Still not done with this one — I'll come back tomorrow, I know how to finish it.",
                topic="the covering-space lifting exercise",
                written_coordinate=None,
                disposition="in_progress",
            )
        ],
        # 06-26: RESOLVED struggle — brutal effort language, but he cracked it → dropped (AC2).
        D26: [
            ExtractedStruggle(
                kind="abandoned_crux",
                verbatim_quote="That was absolutely brutal, but I finally see why the differential drops rank there.",
                topic="why the differential drops rank at a critical point",
                written_coordinate=None,
                disposition="resolved",
            )
        ],
        # 06-28: canonical abandoned crux — names Problem 11.1 → grounded anchor → survives.
        D28: [
            ExtractedStruggle(
                kind="abandoned_crux",
                verbatim_quote="I'll just assume the statement holds — I didn't actually read the proof — and use it.",
                topic="Stokes' theorem on manifolds",
                written_coordinate="Problem 11.1",
                disposition="abandoned",
            )
        ],
    }

    mentions: dict[str, list[ConceptMention]] = {
        # --- the determinant bridge: five distinct, word-disjoint concepts ----
        D19: [
            ConceptMention(
                concept="determinant",
                verbatim_quote="Spent the morning on determinants of linear maps — the alternating multilinear definition.",
                topic="the determinant of a linear map",
            )
        ],
        D20: [
            ConceptMention(
                concept="kernel",
                verbatim_quote="Then rank–nullity, which is really about the kernel of a linear map and its dimension.",
                topic="the kernel of a linear map",
            )
        ],
        D21: [
            ConceptMention(
                concept="SL(m)",
                verbatim_quote="Played with SL(m) today, the matrices of determinant one.",
                topic="the special linear group SL(m)",
            )
        ],
        D22: [
            ConceptMention(
                concept="regular level set",
                verbatim_quote="Regular level sets — the preimage of a regular value is a submanifold.",
                topic="regular level set",
            )
        ],
        D27: [
            ConceptMention(
                concept="submersion",
                verbatim_quote="It clicked: det is a submersion at the identity, so SL(m) is a regular level set — that's why it's a manifold.",
                topic="submersion and regular values",
            )
        ],
        # --- compactness: SAME concept twice, different region (negative control)
        D23: [
            ConceptMention(
                concept="compactness",
                verbatim_quote="Also skimmed compactness of manifolds for the topology track.",
                topic="compactness of a manifold",
            )
        ],
        D26: [
            ConceptMention(
                concept="compactness",
                verbatim_quote="Came back to compactness again — partitions of unity need it.",
                topic="compactness of a manifold",
            )
        ],
    }
    return FakeSignalExtractor(struggles, mentions)


# --- fake verbal-cue reader (#70) ---------------------------------------------


class SeededNightCueReader:
    """An in-memory `NightCueReader` (issue #70) seeded with per-date `NightCue`s.

    Holds what the LLM step *would* have read from each note's transcript about
    the learner's state — is this a distracted/light night? did a concern get
    raised *and* self-closed within the same note? — so #70's deterministic
    restraint policy can be exercised with no model call. Additive to the #69
    fixture: `build_notes` / `build_retrieve` / `build_extractor` are untouched.
    """

    def __init__(self, cues: dict[str, NightCue]) -> None:
        self._cues = cues

    def read(self, note: NoteView) -> NightCue:
        return self._cues.get(note.date, NightCue())


def build_cues() -> SeededNightCueReader:
    """The seeded verbal-cue reader for the corpus (#70).

    Two anti-pattern cues, both read from the note as a whole (model work in
    prod, seeded here):

      * **06-24 distracted.** The note literally opens "Short one today, kind of
        distracted." That light/low-signal verbal cue — NOT its ``brief``
        density_tier — is what silences the day, so a genuine crux still does not
        fire. (Density is only a bar *modifier*; the cue is the gate.)
      * **06-20 self-closed prerequisite.** The 06-20 note flags an unverified IFT
        estimate mid-session ("I'm not sure the estimate is tight — moving on"),
        which #69's per-struggle extractor reads as ``abandoned`` — so a repair
        candidate *is* emitted. But read as a whole, the same note circles back
        and shores the estimate up by the end of the session: a note-level
        self-close. The candidate is therefore **stale** (the prerequisite is
        already closed the same day), and #70 must not fire a card for it. This is
        the note-level holistic read the per-struggle disposition can't capture —
        exactly why it rides the separate cue seam.

    All other dates return a neutral `NightCue()` (no distraction, nothing
    self-closed).
    """
    return SeededNightCueReader(
        {
            D20: NightCue(self_closed_topics=["the inverse function theorem"]),
            D24: NightCue(distracted=True),
        }
    )


# --- notes --------------------------------------------------------------------


def build_notes() -> list[NoteView]:
    """The 10 `NoteView`s of the corpus (in date order)."""
    return [
        NoteView(
            date=D19,
            transcript="Spent the morning on determinants of linear maps — the alternating multilinear definition.",
            concepts=["determinant"],
            density_tier="standard",
            markdown="## Determinants\nThe determinant as an alternating multilinear form.",
        ),
        NoteView(
            date=D20,
            transcript=(
                "Rank–nullity, which is really about the kernel of a linear map and its dimension. "
                "Also I think I proved the inverse function theorem case, but honestly I'm not sure the estimate is tight — moving on."
            ),
            concepts=["kernel", "inverse function theorem"],
            density_tier="standard",
            markdown="## Rank and kernel\nRank–nullity; a proof sketch of the IFT case.",
        ),
        NoteView(
            date=D21,
            transcript="Played with SL(m) today, the matrices of determinant one.",
            concepts=["SL(m)"],
            density_tier="brief",
            markdown="## SL(m)\nThe special linear group.",
        ),
        NoteView(
            date=D22,
            transcript="Regular level sets — the preimage of a regular value is a submanifold.",
            concepts=["regular level set"],
            density_tier="standard",
            markdown="## Regular level sets\nPreimage of a regular value.",
        ),
        NoteView(
            date=D23,
            transcript=(
                "I just used that Fourier convergence trick from that video, not going to prove it, moving on. "
                "Also skimmed compactness of manifolds for the topology track."
            ),
            concepts=["compactness"],
            density_tier="brief",
            markdown="## Odds and ends\nA borrowed trick; a skim of compactness.",
        ),
        NoteView(
            date=D24,
            transcript="Short one today, kind of distracted. Eh, I'll just assume I can diagonalize it and keep going.",
            concepts=["diagonalization"],
            density_tier="brief",  # light day — the trigger is the verbal cue, not density
            markdown="## Quick note\nSkipped the diagonalization details.",
        ),
        NoteView(
            date=D25,
            transcript="Still not done with the covering-space lifting exercise — I'll come back tomorrow, I know how to finish it.",
            concepts=["covering space", "lifting"],
            density_tier="standard",
            dont_spoil=True,  # deliberate in-progress; don't reveal the finish
            markdown="## Lifting exercise (in progress)\nDeliberately unfinished.",
        ),
        NoteView(
            date=D26,
            transcript=(
                "That was absolutely brutal, but I finally see why the differential drops rank there. "
                "Came back to compactness again — partitions of unity need it."
            ),
            concepts=["critical point", "compactness"],
            density_tier="deep",
            markdown="## Breakthrough\nWhy the differential drops rank; compactness revisited.",
        ),
        NoteView(
            date=D27,
            transcript="It clicked: det is a submersion at the identity, so SL(m) is a regular level set — that's why it's a manifold.",
            concepts=["submersion", "regular value"],
            density_tier="standard",
            markdown="## The connection\ndet is a submersion; SL(m) is a regular level set.",
        ),
        NoteView(
            date=D28,
            transcript="I'll just assume the statement holds — I didn't actually read the proof — and use it. Problem 11.1.",
            concepts=["Stokes' theorem"],
            density_tier="standard",
            markdown="## Stokes\nUsed the statement without reading the proof.",
        ),
    ]


# --- the bundle ---------------------------------------------------------------


class Corpus(NamedTuple):
    notes: list[NoteView]
    retrieve: SeededBookRetrieve
    extractor: FakeSignalExtractor
    book_id: str


def build_corpus() -> Corpus:
    """The full corpus bundle — notes + seeded port + seeded extractor + book id."""
    return Corpus(
        notes=build_notes(),
        retrieve=build_retrieve(),
        extractor=build_extractor(),
        book_id=BOOK_ID,
    )

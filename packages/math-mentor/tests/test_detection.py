"""Tests for the detection pass (issue #69) — trailing-window candidate extraction.

Driven entirely through the shared `corpus` module: an in-memory fake
`BookRetrieveFn` (all book access through #68's `resolve_anchor`, never direct)
and an in-memory fake `SignalExtractor` (no model call). Mirrors the
fake-port pattern of `test_resolve_anchor.py`.

Acceptance criteria (issue #69), one or more tests each:
  AC1  every candidate carries a verbatim transcript quote; no quote → no candidate.
  AC2  reads the resolution clause, not effort language (resolved/in-progress ≠ crux).
  AC3  produces the determinant bridge from 06-19→06-27 via retrieval overlap,
       not literal string match.
  AC4  no candidate survives without a resolvable (grounded/section-grounded) anchor.
  AC5  pure extraction — emits the candidate set + anchors; makes no fire/silence
       decision.
"""
from __future__ import annotations

import itertools

import pytest

from mathai.math_mentor.anchor import GroundedAnchor
from mathai.math_mentor.detection import (
    NoteView,
    anchors_overlap,
    detect_candidates,
    from_daily_note,
)
from mathai.math_mentor.signals import (
    CandidateSignal,
    ConceptMention,
    ExtractedStruggle,
    SignalExtractor,
    intent_for_kind,
)

from corpus import (
    BOOK_ID,
    D19,
    D20,
    D23,
    D24,
    D27,
    D28,
    DETERMINANT_CONCEPTS,
    REGION_R,
    FakeSignalExtractor,
    build_corpus,
    build_retrieve,
)


# --- helpers ------------------------------------------------------------------


def run_corpus() -> list[CandidateSignal]:
    notes, retrieve, extractor, book_id = build_corpus()
    return detect_candidates(notes, retrieve, extractor, book_id=book_id)


def by_kind(candidates: list[CandidateSignal], kind: str) -> list[CandidateSignal]:
    return [c for c in candidates if c.kind == kind]


def by_date(candidates: list[CandidateSignal], date: str) -> list[CandidateSignal]:
    return [c for c in candidates if c.source_note_date == date]


# --- the corpus produces exactly the expected candidate set -------------------


def test_corpus_yields_expected_candidate_set() -> None:
    candidates = run_corpus()
    # 06-20 unverified_proof, 06-24 crux, 06-28 crux, + one determinant bridge (06-27).
    kinds = sorted(c.kind for c in candidates)
    assert kinds == ["abandoned_crux", "abandoned_crux", "ripe_bridge", "unverified_proof"]
    assert len(candidates) == 4

    dates = sorted(c.source_note_date for c in candidates)
    assert dates == [D20, D24, D27, D28]


def test_dropped_notes_produce_no_candidate() -> None:
    """The three explicitly-dropped notes contribute nothing:
    06-23 (off-book → ungrounded), 06-25 (in-progress), 06-26 (resolved)."""
    candidates = run_corpus()
    dropped = {"2025-06-23", "2025-06-25", "2025-06-26"}
    assert not [c for c in candidates if c.source_note_date in dropped]


# --- AC1: every candidate carries a verbatim transcript quote -----------------


def test_ac1_every_candidate_has_a_verbatim_quote() -> None:
    for c in run_corpus():
        assert c.verbatim_quote.strip(), f"{c.kind}@{c.source_note_date} has no verbatim quote"


def test_ac1_struggle_without_quote_is_dropped() -> None:
    """A struggle the extractor could not quote (empty verbatim_quote) → no candidate,
    even when it is abandoned AND its anchor would resolve."""
    note = NoteView(date=D28, transcript="mumbling about Stokes", concepts=[])
    quoteless = FakeSignalExtractor(
        struggles={
            D28: [
                ExtractedStruggle(
                    kind="abandoned_crux",
                    verbatim_quote="   ",  # nothing quotable
                    topic="Stokes' theorem on manifolds",
                    written_coordinate="Problem 11.1",  # would ground if it survived
                    disposition="abandoned",
                )
            ]
        },
        mentions={},
    )
    out = detect_candidates([note], build_retrieve(), quoteless, book_id=BOOK_ID)
    assert out == []


def test_ac1_bridge_mention_without_quote_cannot_contribute() -> None:
    """A concept mention with no verbatim quote is dropped before clustering, so a
    would-be bridge that rests on a quoteless mention does not form."""
    notes = [NoteView(date=D19, concepts=["determinant"]), NoteView(date=D27, concepts=["submersion"])]
    ext = FakeSignalExtractor(
        struggles={},
        mentions={
            D19: [ConceptMention(concept="determinant", verbatim_quote="", topic="the determinant of a linear map")],
            D27: [ConceptMention(concept="submersion", verbatim_quote="", topic="submersion and regular values")],
        },
    )
    out = detect_candidates(notes, build_retrieve(), ext, book_id=BOOK_ID)
    assert by_kind(out, "ripe_bridge") == []


# --- AC2: resolution clause, not effort language ------------------------------


def test_ac2_resolved_struggle_is_not_a_crux() -> None:
    """06-26 is heavy on effort language ('absolutely brutal') but its resolution
    clause says he cracked it → disposition 'resolved' → not a candidate."""
    candidates = run_corpus()
    assert by_date(candidates, "2025-06-26") == []


def test_ac2_in_progress_struggle_is_not_a_crux() -> None:
    """06-25 is a deliberate in-progress exercise (dont_spoil) → not abandoned → dropped."""
    candidates = run_corpus()
    assert by_date(candidates, "2025-06-25") == []


@pytest.mark.parametrize("disposition, survives", [("abandoned", True), ("resolved", False), ("in_progress", False)])
def test_ac2_only_abandoned_disposition_survives(disposition: str, survives: bool) -> None:
    """Holding the quote and (resolvable) anchor fixed, ONLY the abandoned
    disposition yields a candidate — proving survival keys on the resolution
    clause, not on the presence of a struggle."""
    note = NoteView(date=D24, transcript="…", concepts=[])
    ext = FakeSignalExtractor(
        struggles={
            D24: [
                ExtractedStruggle(
                    kind="abandoned_crux",
                    verbatim_quote="I'll just assume I can diagonalize it and keep going.",
                    topic="diagonalizing a symmetric matrix",
                    written_coordinate=None,
                    disposition=disposition,  # type: ignore[arg-type]
                )
            ]
        },
        mentions={},
    )
    out = detect_candidates([note], build_retrieve(), ext, book_id=BOOK_ID)
    assert (len(out) == 1) is survives


def test_ac2_verbal_cue_fires_on_a_light_day_not_density() -> None:
    """06-24 is a brief/light day; the crux is caught from the transcript verbal
    cue, not from density — so density is not the trigger."""
    candidates = run_corpus()
    crux = by_date(candidates, D24)
    assert len(crux) == 1
    assert crux[0].kind == "abandoned_crux"
    # It really is a low-density note.
    note_24 = next(n for n in build_corpus().notes if n.date == D24)
    assert note_24.density_tier == "brief"


# --- AC3: determinant bridge via retrieval overlap, not string match ----------


def test_ac3_determinant_bridge_is_produced() -> None:
    candidates = run_corpus()
    bridges = by_kind(candidates, "ripe_bridge")
    assert len(bridges) == 1
    bridge = bridges[0]
    # Ripeness peaks at the latest recurrence in the 06-19→06-27 chain.
    assert bridge.source_note_date == D27
    # Its anchor lands in the shared determinant/regular-level-set region.
    assert bridge.grounded_anchor.heading_path[: len(REGION_R)] == REGION_R
    assert bridge.grounded_anchor.trust_level in {"grounded", "section-grounded"}
    assert bridge.verbatim_quote.strip()


def test_ac3_bridge_concepts_share_no_word_so_literal_match_would_fail() -> None:
    """The five bridging concept strings are pairwise word-disjoint: a naive
    string-overlap clustering could never unite them into one bridge. Only the
    retrieval-anchor overlap does. This guards against a literal-match shortcut."""
    tokens = [set(c.lower().replace("(", " ").replace(")", " ").split()) for c in DETERMINANT_CONCEPTS]
    for a, b in itertools.combinations(tokens, 2):
        assert not (a & b), f"concepts unexpectedly share a token: {a & b}"


def test_ac3_same_concept_recurrence_does_not_bridge() -> None:
    """'compactness' recurs on 06-23 and 06-26 in a *single* region, but it is one
    concept, not two distinct ones → it must NOT form a bridge (distinct-concept
    requirement), even though its two anchors overlap."""
    candidates = run_corpus()
    bridges = by_kind(candidates, "ripe_bridge")
    for b in bridges:
        # No bridge should be anchored in the compactness region.
        assert "§27 Compactness" not in b.grounded_anchor.heading_path


def test_ac3_overlap_is_by_region_not_string() -> None:
    """The overlap primitive keys on skeleton region (shared heading_path prefix
    / same node), independent of the concept strings."""
    a = GroundedAnchor(
        book_id=BOOK_ID, heading_path=[*REGION_R, "Rank and kernel"], query="kernel",
        trust_level="section-grounded", matched=True,
    )
    b = GroundedAnchor(
        book_id=BOOK_ID, heading_path=[*REGION_R, "Example: SL(n)"], query="SL(m)",
        trust_level="section-grounded", matched=True,
    )
    far = GroundedAnchor(
        book_id=BOOK_ID, heading_path=["Chapter 5: Topology of Manifolds", "§27 Compactness", "x"],
        query="compactness", trust_level="section-grounded", matched=True,
    )
    assert anchors_overlap(a, b) is True   # share the 2-level region prefix
    assert anchors_overlap(a, far) is False


# --- AC4: no candidate survives without a resolvable anchor -------------------


def test_ac4_offbook_struggle_is_dropped_for_no_anchor() -> None:
    """06-23's abandoned struggle has a verbatim quote and the right disposition,
    but its topic is off-book → the anchor is ungrounded → no candidate."""
    candidates = run_corpus()
    assert by_date(candidates, D23) == []


def test_ac4_every_candidate_anchor_is_grounded_or_section_grounded() -> None:
    for c in run_corpus():
        assert c.grounded_anchor.trust_level in {"grounded", "section-grounded"}
        assert c.grounded_anchor.trust_level != "ungrounded"
        assert c.grounded_anchor.matched is True


def test_ac4_grounded_vs_section_grounded_mix() -> None:
    """06-28 names a coordinate (Problem 11.1) → grounded; the light-day crux and
    the bridge are topical → section-grounded."""
    candidates = run_corpus()
    crux_28 = by_date(candidates, D28)[0]
    assert crux_28.grounded_anchor.trust_level == "grounded"
    assert crux_28.grounded_anchor.label == "Problem 11.1"

    crux_24 = by_date(candidates, D24)[0]
    assert crux_24.grounded_anchor.trust_level == "section-grounded"
    assert crux_24.grounded_anchor.label is None  # no false precision


# --- AC5: pure extraction (no fire/silence decision) --------------------------


def test_ac5_output_is_a_set_of_candidate_signals_only() -> None:
    """The pass returns CandidateSignals — no accept/silence verdict field, no
    decision. dont_spoil (06-25 would-be) is a #70 concern, not a detection one."""
    candidates = run_corpus()
    assert all(isinstance(c, CandidateSignal) for c in candidates)
    # The contract carries exactly the #69 fields — nothing decision-shaped.
    assert set(CandidateSignal.model_fields) == {
        "kind", "verbatim_quote", "topic", "written_coordinate", "source_note_date", "grounded_anchor",
    }


def test_ac5_extraction_is_deterministic_and_stable() -> None:
    assert run_corpus() == run_corpus()


def test_ac5_detection_never_calls_a_model_only_the_injected_seams() -> None:
    """Both data sources are injected fakes; the port is the only book access and
    it is actually exercised (proving grounding rides through resolve_anchor)."""
    notes, retrieve, extractor, book_id = build_corpus()
    detect_candidates(notes, retrieve, extractor, book_id=book_id)
    assert len(retrieve.calls) > 0
    # Every retrieval was book-scoped to Tu through the resolver.
    assert all(req.book_id == BOOK_ID for req in retrieve.calls)


# --- intent mapping (open seam) -----------------------------------------------


def test_intent_mapping_per_kind() -> None:
    assert intent_for_kind("abandoned_crux") == "theorem"
    assert intent_for_kind("unverified_proof") == "proof"
    assert intent_for_kind("ripe_bridge") == "general"


def test_resolver_receives_kind_appropriate_intent() -> None:
    """The intent forwarded into book_retrieve matches the candidate's kind."""
    notes, retrieve, extractor, book_id = build_corpus()
    detect_candidates(notes, retrieve, extractor, book_id=book_id)
    # 06-28's crux query is the coordinate 'Problem 11.1' with a theorem intent.
    crux_reqs = [r for r in retrieve.calls if (r.query or "").lower() == "problem 11.1"]
    assert crux_reqs and all(r.intent == "theorem" for r in crux_reqs)
    # The proof repair (06-20) resolves with a proof intent.
    proof_reqs = [r for r in retrieve.calls if "inverse function theorem" in (r.query or "").lower()]
    assert proof_reqs and all(r.intent == "proof" for r in proof_reqs)
    # Bridge mentions resolve with the general intent.
    bridge_reqs = [r for r in retrieve.calls if "determinant" in (r.query or "").lower()]
    assert bridge_reqs and all(r.intent == "general" for r in bridge_reqs)


# --- trailing window (open seam) ----------------------------------------------


def test_trailing_window_limits_to_most_recent_notes() -> None:
    """A window of 2 keeps only 06-27 and 06-28 → the bridge (needs the earlier
    chain) disappears; the 06-28 crux remains."""
    notes, retrieve, extractor, book_id = build_corpus()
    out = detect_candidates(notes, retrieve, extractor, book_id=book_id, window=2)
    assert by_kind(out, "ripe_bridge") == []
    assert [c.source_note_date for c in out] == [D28]


def test_full_window_is_the_default() -> None:
    notes, retrieve, extractor, book_id = build_corpus()
    assert detect_candidates(notes, retrieve, extractor, book_id=book_id) == run_corpus()


# --- read-model adapter (thin platform → NoteView) ----------------------------


def test_from_daily_note_maps_the_fields_detection_reads() -> None:
    """`from_daily_note` mirrors the real DailyNoteArtifact (+ flairs) into a NoteView."""
    from mathai.math_notes.artifacts import DailyNoteArtifact, NoteSynthesis, NoteMagnitude
    from mathai.math_notes.models import NoteFlair

    artifact = DailyNoteArtifact(
        note_date="2025-06-27",
        transcript="det is a submersion at the identity…",
        synthesis=NoteSynthesis(
            markdown="## The connection\n$\\det$ is a submersion.",
            concepts=["submersion", "regular value"],
        ),
        magnitude=NoteMagnitude(density_tier="deep"),
    )
    view = from_daily_note(artifact, flairs=[NoteFlair.dont_spoil])

    assert view.date == "2025-06-27"
    assert view.transcript == "det is a submersion at the identity…"
    assert view.concepts == ["submersion", "regular value"]
    assert view.density_tier == "deep"
    assert view.dont_spoil is True
    assert view.markdown.startswith("## The connection")


def test_from_daily_note_defaults_when_optional_parts_absent() -> None:
    from mathai.math_notes.artifacts import DailyNoteArtifact

    view = from_daily_note(DailyNoteArtifact(note_date="2025-06-19", transcript="hi"))
    assert view.concepts == []
    assert view.markdown is None
    assert view.density_tier == "standard"
    assert view.dont_spoil is False


# --- fakes satisfy the ports --------------------------------------------------


def test_fake_extractor_satisfies_the_signal_extractor_protocol() -> None:
    assert isinstance(FakeSignalExtractor({}, {}), SignalExtractor)

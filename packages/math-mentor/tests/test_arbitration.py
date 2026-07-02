"""Tests for restraint & arbitration (issue #70) — the IF and the WHICH.

Driven off the shared `corpus` module (#69's 10-note fixture, extended additively
with `build_cues()` — the seeded verbal-cue reader). Every book access rides
through #68's `resolve_anchor` via an in-memory fake `BookRetrieveFn`; the
verbal-cue and signal seams are in-memory fakes too — **no** model call anywhere.

Acceptance criteria (issue #70), one or more tests each:
  AC1  Fires on 06-28 (one abandoned-crux, high confidence, quoted hedge +
       grounded anchor).
  AC2  Silent on 06-24 / 06-25 / 06-26; not stale on 06-20.
  AC3  ≤2 cards across the 10 notes; never two in one night.
  AC4  Below-bar signal → no card.
  AC5  Repeated ignores → back off / raise the bar (never escalate).
  AC6  Every fire carries a verbatim quote and a non-ungrounded anchor.

Plus the policy mechanics the ACs rest on: the `MentorDecision` contract + kind
mapping, one-card-max arbitration with loser preservation, the adversarial
self-check (re-resolve → ungrounded ⇒ no fire), the corpus-cap backstop, and that
grounding rides ONLY through `resolve_anchor`.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mathai.math_book.models import BookRetrievalHit, BookRetrievalResult, BookRetrieveInput
from mathai.math_mentor.anchor import GroundedAnchor, resolve_anchor
from mathai.math_mentor.arbitration import (
    BASE_BAR,
    IGNORE_STEP,
    MAX_CORPUS_CARDS,
    MentorDecision,
    MentorState,
    NightCue,
    NightCueReader,
    arbitrate,
    candidate_confidence,
    confidence_bar,
    drive_corpus,
)
from mathai.math_mentor.detection import NoteView
from mathai.math_mentor.signals import CandidateSignal, intent_for_kind

from corpus import (
    BOOK_ID,
    D20,
    D24,
    D25,
    D26,
    D27,
    D28,
    ExtractedStruggle,
    FakeSignalExtractor,
    SeededBookRetrieve,
    SeededNightCueReader,
    build_corpus,
    build_cues,
    build_retrieve,
)


# --- helpers ------------------------------------------------------------------


def make_candidate(
    kind: str,
    topic: str,
    *,
    retrieve,
    date: str,
    quote: str,
    coordinate: str | None = None,
) -> CandidateSignal:
    """Build a `CandidateSignal` with a *real* anchor resolved through #68.

    Uses the same resolver detection would — so the candidate's anchor trust is
    honest (grounded / section-grounded), not hand-fabricated.
    """
    anchor = resolve_anchor(
        retrieve,
        book_id=BOOK_ID,
        coordinate=coordinate,
        topic=topic,
        intent=intent_for_kind(kind),  # type: ignore[arg-type]
    )
    return CandidateSignal(
        kind=kind,  # type: ignore[arg-type]
        verbatim_quote=quote,
        topic=topic,
        written_coordinate=coordinate,
        source_note_date=date,
        grounded_anchor=anchor,
    )


def drive_the_corpus(*, ignored_dates=None) -> dict[str, MentorDecision]:
    """Drive the full corpus (with its seeded cues) → {date: decision}."""
    notes, retrieve, extractor, book_id = build_corpus()
    cues = build_cues()
    decisions = drive_corpus(
        notes, retrieve, extractor, book_id=book_id, cues=cues, ignored_dates=ignored_dates
    )
    ordered = sorted(notes, key=lambda n: n.date)
    return {n.date: d for n, d in zip(ordered, decisions)}


class _CoordinateGrounder:
    """A tiny `BookRetrieveFn` that grounds ANY coordinate (label == the query)."""

    def __init__(self) -> None:
        self.calls: list[BookRetrieveInput] = []

    def __call__(self, req: BookRetrieveInput) -> BookRetrievalResult:
        self.calls.append(req)
        return BookRetrievalResult(
            book_id=req.book_id,
            query=req.query,
            hits=[
                BookRetrievalHit(
                    chunk_id="c",
                    node_id=f"n-{req.query}",
                    text="body",
                    score=0.9,
                    label=req.query,  # equals the coordinate → grounded
                    page=1,
                    heading_path=["Chapter X", "§Y"],
                    source="src",
                )
            ],
        )


# =============================================================================
# AC1 — fires on 06-28
# =============================================================================


def test_ac1_fires_on_06_28() -> None:
    """06-28: one abandoned_crux, grounded (coordinate) anchor, quoted hedge → FIRE."""
    decisions = drive_the_corpus()
    d = decisions[D28]
    assert d.fire is True
    assert d.kind == "repair"  # abandoned_crux → repair
    assert d.winning_signal is not None
    assert d.winning_signal.kind == "abandoned_crux"
    # High confidence: the anchor is grounded on an exact coordinate label.
    assert d.grounded_anchor is not None
    assert d.grounded_anchor.trust_level == "grounded"
    assert d.grounded_anchor.label == "Problem 11.1"
    # A quoted hedge rides along.
    assert d.quote and d.quote.strip()
    assert d.quote == d.winning_signal.verbatim_quote


# =============================================================================
# AC2 — silent on 06-24 / 06-25 / 06-26; not stale on 06-20
# =============================================================================


def test_ac2_silent_on_06_24_distracted_verbal_cue() -> None:
    """06-24 is a real crux (section-grounded), but the VERBAL CUE is 'distracted'
    → silence. It is silenced by the cue, NOT by its brief density_tier."""
    decisions = drive_the_corpus()
    d = decisions[D24]
    assert d.fire is False
    assert d.kind == "none"
    assert "distracted" in d.reason
    # The candidate is preserved, not discarded.
    assert len(d.suppressed) == 1
    assert d.suppressed[0].kind == "abandoned_crux"


def test_ac2_silent_on_06_25_and_06_26_no_candidate() -> None:
    """06-25 (in-progress + dont_spoil) and 06-26 (resolved) yield no candidate
    from #69 → silent by construction."""
    decisions = drive_the_corpus()
    for date in (D25, D26):
        assert decisions[date].fire is False
        assert decisions[date].kind == "none"
        assert decisions[date].suppressed == []


def test_ac2_not_stale_on_06_20_self_closed_same_day() -> None:
    """06-20's unverified_proof IS a candidate (#69 emits it), but the note-level
    cue says the IFT estimate was self-closed the same day → stale → no card."""
    decisions = drive_the_corpus()
    d = decisions[D20]
    assert d.fire is False
    assert d.kind == "none"
    assert "stale" in d.reason
    # Preserved for a later pass, never discarded.
    assert len(d.suppressed) == 1
    assert d.suppressed[0].kind == "unverified_proof"


def test_ac2_without_the_self_close_cue_06_20_would_fire() -> None:
    """Proof the staleness gate is load-bearing: absent the self-closed cue, the
    same 06-20 candidate clears the bar and fires — so the silence is the gate's
    doing, not a below-bar accident."""
    notes, retrieve, extractor, book_id = build_corpus()
    # Neutral cues everywhere (no self-close, no distraction).
    neutral = SeededNightCueReader({})
    decisions = drive_corpus(notes, retrieve, extractor, book_id=book_id, cues=neutral)
    by_date = {n.date: d for n, d in zip(sorted(notes, key=lambda n: n.date), decisions)}
    assert by_date[D20].fire is True
    assert by_date[D20].kind == "repair"


# =============================================================================
# AC3 — ≤2 cards across the 10 notes; never two in one night
# =============================================================================


def test_ac3_at_most_two_cards_across_the_corpus() -> None:
    decisions = list(drive_the_corpus().values())
    fires = [d for d in decisions if d.fire]
    assert len(fires) <= MAX_CORPUS_CARDS
    # The canonical corpus fires exactly two: the 06-27 bridge and the 06-28 repair.
    assert {d.winning_signal.source_note_date for d in fires} == {D27, D28}


def test_ac3_never_two_cards_in_one_night() -> None:
    """Every decision is structurally one card: a single `winning_signal`, and at
    most one fire per night across the whole drive."""
    decisions = drive_the_corpus()
    for date, d in decisions.items():
        if d.fire:
            assert d.winning_signal is not None
            assert d.kind in ("repair", "bridge")
        else:
            assert d.winning_signal is None
    # One decision per note; a decision can never represent two cards.
    assert len(decisions) == 10


def test_ac3_corpus_cap_is_a_hard_backstop() -> None:
    """Even if three grounded cruxes surface on three nights, only two fire — the
    third hits the corpus-card budget and is (preserved but) silenced."""
    grounder = _CoordinateGrounder()
    dates = ["2025-07-01", "2025-07-02", "2025-07-03"]
    coords = ["Problem 3.1", "Problem 3.2", "Problem 3.3"]
    notes = [NoteView(date=d, density_tier="standard") for d in dates]
    struggles = {
        d: [
            ExtractedStruggle(
                kind="abandoned_crux",
                verbatim_quote=f"assuming {c} and moving on",
                topic=f"topic for {c}",
                written_coordinate=c,
                disposition="abandoned",
            )
        ]
        for d, c in zip(dates, coords)
    }
    ext = FakeSignalExtractor(struggles=struggles, mentions={})
    decisions = drive_corpus(notes, grounder, ext, book_id=BOOK_ID)
    fires = [d for d in decisions if d.fire]
    assert len(fires) == MAX_CORPUS_CARDS  # exactly two, not three
    assert decisions[2].fire is False
    assert "budget" in decisions[2].reason


def test_ac3_cap_binds_at_the_arbitrate_level() -> None:
    """With the budget already spent, arbitrate refuses to fire a strong candidate
    — and still preserves it."""
    retrieve = build_retrieve()
    cand = make_candidate(
        "abandoned_crux",
        "Stokes' theorem on manifolds",
        retrieve=retrieve,
        date=D28,
        quote="assume it holds and move on",
        coordinate="Problem 11.1",
    )
    note = NoteView(date=D28, density_tier="standard")
    spent = MentorState(cards_fired=MAX_CORPUS_CARDS)
    d = arbitrate([cand], note=note, retrieve=retrieve, history=spent)
    assert d.fire is False
    assert "budget" in d.reason
    assert d.suppressed == [cand]
    # One slot free → the same candidate fires.
    one_left = MentorState(cards_fired=MAX_CORPUS_CARDS - 1)
    assert arbitrate([cand], note=note, retrieve=retrieve, history=one_left).fire is True


# =============================================================================
# AC4 — below-bar signal → no card
# =============================================================================


def test_ac4_below_bar_signal_produces_no_card() -> None:
    """A section-grounded candidate on a brief night falls below the confidence
    bar (weak anchor + light night) → silence, no hedged low-confidence card."""
    retrieve = build_retrieve()
    cand = make_candidate(
        "unverified_proof",
        "the inverse function theorem",  # section-grounded (no coordinate)
        retrieve=retrieve,
        date=D20,
        quote="not sure the estimate is tight, moving on",
    )
    assert cand.grounded_anchor.trust_level == "section-grounded"
    brief = NoteView(date=D20, density_tier="brief")
    # section-grounded (0.6) + brief (-0.15) = 0.45 < BASE_BAR (0.55)
    assert candidate_confidence(cand, brief) < BASE_BAR
    d = arbitrate([cand], note=brief, retrieve=retrieve)
    assert d.fire is False
    assert "below the confidence bar" in d.reason
    assert d.suppressed == [cand]


def test_ac4_same_candidate_clears_the_bar_on_a_standard_night() -> None:
    """Contrast: the identical section-grounded candidate DOES clear the bar on a
    standard night — so the below-bar silence is about the night, not the kind."""
    retrieve = build_retrieve()
    cand = make_candidate(
        "unverified_proof",
        "the inverse function theorem",
        retrieve=retrieve,
        date=D20,
        quote="not sure the estimate is tight, moving on",
    )
    standard = NoteView(date=D20, density_tier="standard")
    assert candidate_confidence(cand, standard) >= BASE_BAR
    assert arbitrate([cand], note=standard, retrieve=retrieve).fire is True


# =============================================================================
# AC5 — repeated ignores → back off / raise the bar (never escalate)
# =============================================================================


def test_ac5_confidence_bar_only_rises_never_falls() -> None:
    bars = [confidence_bar(i) for i in range(6)]
    # Strictly rising on ignores → backing off; never below the base → never escalating.
    assert bars == sorted(bars)
    assert all(b >= BASE_BAR for b in bars)
    assert all(bars[i + 1] > bars[i] for i in range(len(bars) - 1))
    assert confidence_bar(0) == BASE_BAR
    assert confidence_bar(2) == pytest.approx(BASE_BAR + 2 * IGNORE_STEP)
    # A negative/zero streak never dips below the base (never escalate).
    assert confidence_bar(-5) == BASE_BAR


def test_ac5_repeated_ignores_back_off_a_borderline_card() -> None:
    """Two identical section-grounded nights. With no ignores both fire; once the
    first card is ignored the bar rises and the second (borderline) night stays
    silent. Fewer cards, never more — the mentor backs off, never escalates."""
    retrieve = build_retrieve()
    d1, d2 = "2025-07-01", "2025-07-02"
    notes = [NoteView(date=d1, density_tier="standard"), NoteView(date=d2, density_tier="standard")]
    ext = FakeSignalExtractor(
        struggles={
            d1: [
                ExtractedStruggle(
                    kind="unverified_proof",
                    verbatim_quote="q1 — not sure the estimate is tight, moving on",
                    topic="the inverse function theorem",
                    written_coordinate=None,
                    disposition="abandoned",
                )
            ],
            d2: [
                ExtractedStruggle(
                    kind="unverified_proof",
                    verbatim_quote="q2 — still not sure the estimate is tight, moving on",
                    topic="the inverse function theorem",
                    written_coordinate=None,
                    disposition="abandoned",
                )
            ],
        },
        mentions={},
    )

    no_ignores = drive_corpus(notes, retrieve, ext, book_id=BOOK_ID)
    assert [d.fire for d in no_ignores] == [True, True]  # both borderline cards land

    ignored = drive_corpus(notes, retrieve, ext, book_id=BOOK_ID, ignored_dates={d1})
    assert ignored[0].fire is True  # the first still fires...
    assert ignored[1].fire is False  # ...but the ignore raised the bar → back off
    assert "below the confidence bar" in ignored[1].reason
    # Strictly fewer cards under ignores — never more.
    assert sum(d.fire for d in ignored) < sum(d.fire for d in no_ignores)


def test_ac5_a_landed_card_resets_the_streak() -> None:
    """State bookkeeping: a fired card that is NOT ignored resets the streak to 0
    (only fired-then-ignored cards accumulate)."""
    st = MentorState(cards_fired=1, consecutive_ignores=3)
    # Simulate the driver's reset on a landed card.
    landed = MentorState(cards_fired=st.cards_fired + 1, consecutive_ignores=0)
    assert confidence_bar(landed.consecutive_ignores) == BASE_BAR


# =============================================================================
# AC6 — every fire carries a verbatim quote and a non-ungrounded anchor
# =============================================================================


def test_ac6_every_fire_has_a_quote_and_non_ungrounded_anchor() -> None:
    for d in drive_the_corpus().values():
        if d.fire:
            assert d.quote and d.quote.strip(), "a fired card must carry a verbatim quote"
            assert d.grounded_anchor is not None
            assert d.grounded_anchor.trust_level in {"grounded", "section-grounded"}
            assert d.grounded_anchor.trust_level != "ungrounded"
            assert d.grounded_anchor.matched is True
            # The quote is the winner's verbatim span.
            assert d.quote == d.winning_signal.verbatim_quote


# =============================================================================
# The adversarial self-check — grounding gates the fire (issue's hard rule)
# =============================================================================


def test_self_check_reresolves_through_resolve_anchor_only() -> None:
    """A firing decision re-resolves the winner's anchor via the injected port —
    proving the self-check rides through #68's resolver, not a side channel."""
    retrieve = build_retrieve()
    cand = make_candidate(
        "abandoned_crux",
        "Stokes' theorem on manifolds",
        retrieve=retrieve,
        date=D28,
        quote="assume it holds and move on",
        coordinate="Problem 11.1",
    )
    note = NoteView(date=D28, density_tier="standard")
    calls_before = len(retrieve.calls)
    d = arbitrate([cand], note=note, retrieve=retrieve)
    assert d.fire is True
    # The self-check made a fresh retrieval for the winner's coordinate.
    new_calls = retrieve.calls[calls_before:]
    assert any((r.query or "").lower() == "problem 11.1" for r in new_calls)
    assert all(r.book_id == BOOK_ID for r in new_calls)  # book-scoped


def test_self_check_ungrounded_reresolve_cannot_fire() -> None:
    """If the anchor no longer resolves (empty retrieval on re-check), the card
    cannot fire — we won't point at a directive we can't ground."""
    resolving = build_retrieve()
    cand = make_candidate(
        "abandoned_crux",
        "diagonalizing a symmetric matrix",  # section-grounded at build time
        retrieve=resolving,
        date=D24,
        quote="I'll just assume I can diagonalize it and keep going.",
    )
    assert cand.grounded_anchor.trust_level == "section-grounded"
    note = NoteView(date=D24, density_tier="standard")  # standard so it clears the bar
    empty = SeededBookRetrieve([])  # re-resolve returns nothing → ungrounded
    d = arbitrate([cand], note=note, retrieve=empty)
    assert d.fire is False
    assert "self-check" in d.reason
    assert d.suppressed == [cand]


# =============================================================================
# One-card-max arbitration — live repair > ripe bridge, losers preserved
# =============================================================================


def test_one_card_max_repair_beats_bridge_and_bridge_is_preserved() -> None:
    """Two candidates in ONE night — a live repair and a ripe bridge. The repair
    wins; the bridge is carried in `suppressed`, never discarded."""
    retrieve = build_retrieve()
    repair = make_candidate(
        "unverified_proof",
        "the inverse function theorem",
        retrieve=retrieve,
        date=D27,
        quote="not sure the estimate is tight, moving on",
    )
    bridge = make_candidate(
        "ripe_bridge",
        "submersion and regular values",
        retrieve=retrieve,
        date=D27,
        quote="det is a submersion, so SL(m) is a regular level set",
    )
    note = NoteView(date=D27, density_tier="standard")
    d = arbitrate([bridge, repair], note=note, retrieve=retrieve)  # order shouldn't matter
    assert d.fire is True
    assert d.kind == "repair"
    assert d.winning_signal is repair
    assert d.suppressed == [bridge]  # the loser is preserved


def test_kind_mapping_covers_every_candidate_kind() -> None:
    retrieve = build_retrieve()
    note = NoteView(date=D27, density_tier="standard")
    proof = make_candidate(
        "unverified_proof", "the inverse function theorem", retrieve=retrieve, date=D27, quote="q"
    )
    crux = make_candidate(
        "abandoned_crux", "Stokes' theorem on manifolds", retrieve=retrieve, date=D28,
        quote="q", coordinate="Problem 11.1",
    )
    bridge = make_candidate(
        "ripe_bridge", "submersion and regular values", retrieve=retrieve, date=D27, quote="q"
    )
    assert arbitrate([proof], note=note, retrieve=retrieve).kind == "repair"
    assert arbitrate([crux], note=note, retrieve=retrieve).kind == "repair"
    assert arbitrate([bridge], note=note, retrieve=retrieve).kind == "bridge"
    # Nothing to decide → none.
    assert arbitrate([], note=note, retrieve=retrieve).kind == "none"


# =============================================================================
# Anti-pattern: dont_spoil flair
# =============================================================================


def test_dont_spoil_flair_suppresses_even_a_present_candidate() -> None:
    """A note carrying the dont_spoil flair silences the night even when a strong
    candidate is present — respect the learner's deliberate in-progress work."""
    retrieve = build_retrieve()
    cand = make_candidate(
        "abandoned_crux",
        "Stokes' theorem on manifolds",
        retrieve=retrieve,
        date=D25,
        quote="assume it holds",
        coordinate="Problem 11.1",  # would otherwise be a strong grounded fire
    )
    spoil_note = NoteView(date=D25, density_tier="standard", dont_spoil=True)
    d = arbitrate([cand], note=spoil_note, retrieve=retrieve)
    assert d.fire is False
    assert "dont_spoil" in d.reason
    assert d.suppressed == [cand]


# =============================================================================
# The MentorDecision contract
# =============================================================================


def test_mentor_decision_shape_and_extra_forbid() -> None:
    assert set(MentorDecision.model_fields) == {
        "fire", "kind", "winning_signal", "grounded_anchor", "quote", "suppressed", "reason",
    }
    with pytest.raises(ValidationError):
        MentorDecision(fire=False, kind="none", reason="x", nope=1)  # type: ignore[call-arg]


def test_silent_decision_is_fully_null_but_preserves_candidates() -> None:
    """A no-candidate night: everything decision-shaped is null, suppressed empty."""
    d = arbitrate([], note=NoteView(date=D28), retrieve=build_retrieve())
    assert d.fire is False
    assert d.kind == "none"
    assert d.winning_signal is None
    assert d.grounded_anchor is None
    assert d.quote is None
    assert d.suppressed == []


def test_driver_returns_one_decision_per_note_in_date_order() -> None:
    notes, retrieve, extractor, book_id = build_corpus()
    decisions = drive_corpus(notes, retrieve, extractor, book_id=book_id, cues=build_cues())
    assert len(decisions) == len(notes)
    assert all(isinstance(d, MentorDecision) for d in decisions)


# =============================================================================
# Seams satisfy their protocols; determinism
# =============================================================================


def test_seeded_cue_reader_satisfies_the_protocol() -> None:
    assert isinstance(build_cues(), NightCueReader)
    assert isinstance(SeededNightCueReader({}), NightCueReader)


def test_neutral_cue_when_unseeded() -> None:
    reader = SeededNightCueReader({})
    cue = reader.read(NoteView(date="2025-01-01"))
    assert cue == NightCue()
    assert cue.distracted is False
    assert cue.self_closed_topics == []


def test_arbitration_is_deterministic() -> None:
    a = [(d.fire, d.kind, d.reason) for d in drive_the_corpus().values()]
    b = [(d.fire, d.kind, d.reason) for d in drive_the_corpus().values()]
    assert a == b


def test_grounding_only_rides_through_resolve_anchor() -> None:
    """The whole drive touches the book solely through the injected port (which is
    exercised) — never a direct store."""
    notes, retrieve, extractor, book_id = build_corpus()
    drive_corpus(notes, retrieve, extractor, book_id=book_id, cues=build_cues())
    assert len(retrieve.calls) > 0
    assert all(r.book_id == BOOK_ID for r in retrieve.calls)

"""Tests for the repair card compose + tone gate (issue #71).

Driven off the shared `corpus` module (#69's 10-note fixture, extended additively
with `build_card_writer()` — the seeded `CardWriter` — and `build_unverified_proof_note()`).
Every book access rides through #68's `resolve_anchor` via an in-memory fake
`BookRetrieveFn`; the generative strings ride the in-memory fake writer — **no**
model call anywhere. `compose_repair_card` itself never retrieves.

Two flavors of one shape are exercised end-to-end:

  * ``abandonment`` (06-28, ``abandoned_crux``, **grounded** coordinate anchor),
  * ``unverified_proof`` (06-27 IFT, **section-grounded** anchor),

plus an ``abandonment`` / section-grounded degradation and an
``unverified_proof`` / grounded case, so both flavors cover both trust levels.

Acceptance criteria (issue #71), one or more tests each:
  * Names the **specific step**, not the topic; **quotes him**; one-line
    why-it-matters a mathematician would sign.
  * **Exactly one** move, book-anchored, one sitting, **never the answer**.
  * Celebrates one **specific real** thing from the same note; concrete **when**.
  * ~4 lines / ~10s; passes the **human-tutor gate**.
  * Degrades gracefully: ``grounded`` → exact label; ``section-grounded`` →
    section, **no** fake number; ``ungrounded`` → **refuses** (never invents one).
  * Both flavors compose.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mathai.math_book.models import BookRetrieveInput
from mathai.math_mentor.anchor import GroundedAnchor, resolve_anchor
from mathai.math_mentor.arbitration import (
    MentorDecision,
    arbitrate,
    drive_corpus,
)
from mathai.math_mentor.detection import NoteView
from mathai.math_mentor.repair_card import (
    MAX_CARD_CHARS,
    MAX_CARD_LINES,
    MAX_WHY_CHARS,
    CardWriter,
    MentorCard,
    ToneGateError,
    assert_tone_gate,
    compose_repair_card,
    passes_tone_gate,
    render_citation,
    tone_gate_violations,
)
from mathai.math_mentor.signals import CandidateSignal, intent_for_kind

from corpus import (
    BOOK_ID,
    D24,
    D27,
    D28,
    SeededBookRetrieve,
    SeededCardWriter,
    build_card_writer,
    build_corpus,
    build_cues,
    build_retrieve,
    build_unverified_proof_note,
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
    """A `CandidateSignal` with a *real* anchor resolved through #68 (honest trust)."""
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


def _fire(cand: CandidateSignal, note: NoteView, retrieve) -> MentorDecision:
    """Arbitrate a single candidate on a standard night and assert it fired repair."""
    d = arbitrate([cand], note=note, retrieve=retrieve)
    assert d.fire is True and d.kind == "repair"
    return d


# --- scenario factories (decision, note) --------------------------------------


def abandonment_grounded() -> tuple[MentorDecision, NoteView]:
    """06-28 from the real corpus drive: abandoned_crux, grounded coordinate anchor."""
    notes, retrieve, extractor, book_id = build_corpus()
    decisions = drive_corpus(notes, retrieve, extractor, book_id=book_id, cues=build_cues())
    by_date = {n.date: d for n, d in zip(sorted(notes, key=lambda n: n.date), decisions)}
    note = next(n for n in notes if n.date == D28)
    return by_date[D28], note


def unverified_proof_section() -> tuple[MentorDecision, NoteView]:
    """06-27 standalone: an unverified IFT proof → section-grounded anchor."""
    retrieve = build_retrieve()
    note = build_unverified_proof_note()
    cand = make_candidate(
        "unverified_proof",
        "the inverse function theorem",
        retrieve=retrieve,
        date=D27,
        quote="I'm honestly not sure the estimate is tight — moving on",
    )
    assert cand.grounded_anchor.trust_level == "section-grounded"
    return _fire(cand, note, retrieve), note


def abandonment_section() -> tuple[MentorDecision, NoteView]:
    """An abandoned crux whose anchor is only section-grounded (diagonalization)."""
    retrieve = build_retrieve()
    note = NoteView(
        date=D24,
        density_tier="standard",
        markdown="## Diagonalization\nAssumed the symmetric matrix diagonalizes; skipped the details.",
        transcript="I'll just assume I can diagonalize it and keep going.",
    )
    cand = make_candidate(
        "abandoned_crux",
        "diagonalizing a symmetric matrix",
        retrieve=retrieve,
        date=D24,
        quote="I'll just assume I can diagonalize it and keep going.",
    )
    assert cand.grounded_anchor.trust_level == "section-grounded"
    return _fire(cand, note, retrieve), note


def unverified_proof_grounded() -> tuple[MentorDecision, NoteView]:
    """An unverified proof that names a coordinate → grounded anchor."""
    retrieve = build_retrieve()
    note = NoteView(
        date=D27,
        density_tier="standard",
        markdown="## Stokes proof\nWrote the proof but never checked the boundary term.",
        transcript="I wrote out the proof but didn't verify the boundary term — moving on.",
    )
    cand = make_candidate(
        "unverified_proof",
        "Stokes' theorem on manifolds",
        retrieve=retrieve,
        date=D27,
        quote="I wrote out the proof but didn't verify the boundary term — moving on.",
        coordinate="Problem 11.1",
    )
    assert cand.grounded_anchor.trust_level == "grounded"
    return _fire(cand, note, retrieve), note


#: name → (factory, expected flavor, expected trust). Parametrizes the AC sweep.
SCENARIOS = [
    ("abandonment_grounded", abandonment_grounded, "abandonment", "grounded"),
    ("unverified_proof_section", unverified_proof_section, "unverified_proof", "section-grounded"),
    ("abandonment_section", abandonment_section, "abandonment", "section-grounded"),
    ("unverified_proof_grounded", unverified_proof_grounded, "unverified_proof", "grounded"),
]
_IDS = [s[0] for s in SCENARIOS]


def _compose(factory) -> tuple[MentorCard, MentorDecision, NoteView]:
    decision, note = factory()
    card = compose_repair_card(decision, note, build_card_writer())
    return card, decision, note


# =============================================================================
# Both flavors compose (+ trust levels)
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_both_flavors_compose(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    assert isinstance(card, MentorCard)
    assert card.flavor == flavor
    assert card.trust_level == trust
    assert card.source_note_date == decision.winning_signal.source_note_date


# =============================================================================
# AC — quotes him
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_catch_is_his_verbatim_quote(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    assert card.catch and card.catch.strip()
    assert card.catch == decision.quote
    assert card.catch == decision.winning_signal.verbatim_quote


# =============================================================================
# AC — names the specific step, not the topic
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_move_names_specific_step_not_topic(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    topic = decision.winning_signal.topic
    # The move is not merely the topic restated…
    assert card.move.strip().lower() != topic.strip().lower()
    # …and stripping the citation still leaves a named step (not nothing).
    without_citation = card.move.replace(card.citation, "").strip(" ,.—-")
    assert without_citation
    assert without_citation.lower() != topic.strip().lower()


# =============================================================================
# AC — one-line why-it-matters a mathematician would sign
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_why_it_matters_is_one_line(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    assert card.why_it_matters and card.why_it_matters.strip()
    assert "\n" not in card.why_it_matters
    assert len(card.why_it_matters) <= MAX_WHY_CHARS


# =============================================================================
# AC — exactly one move, book-anchored, one sitting, never the answer
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_exactly_one_move_book_anchored_never_the_answer(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    # Book-anchored: the move carries the rendered citation, exactly once.
    assert card.citation and card.citation.strip()
    assert card.citation in card.move
    assert card.move.count(card.citation) == 1
    # It directs an action (reread / redo / do / verify …), and never solves.
    assert any(v in card.move.lower() for v in ("reread", "redo", "do ", "verify", "rebuild", "check", "work"))
    for spoiler in ("the answer is", "the solution is", "q.e.d"):
        assert spoiler not in card.move.lower()


# =============================================================================
# AC — celebrates one specific real thing from the SAME note
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_celebration_is_specific_and_from_the_same_note(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    assert card.on_his_side and card.on_his_side.strip()
    # Not generic praise.
    for generic in ("good job", "great work", "keep it up", "well done", "nice work"):
        assert generic not in card.on_his_side.lower()
    # Drawn from THIS note: it shares a substantive token with the note text.
    import re

    def toks(s: str) -> set[str]:
        return set(re.findall(r"[a-z][a-z'-]{3,}", s.lower()))

    note_blob = " ".join(filter(None, [note.markdown or "", note.transcript or ""]))
    assert toks(card.on_his_side) & toks(note_blob)


# =============================================================================
# AC — concrete when (the close)
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_close_names_a_concrete_when(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    assert card.close and card.close.strip()
    assert "sunday" in card.close.lower()  # default check_in


def test_check_in_is_configurable() -> None:
    decision, note = abandonment_grounded()
    card = compose_repair_card(decision, note, build_card_writer(), check_in="Thursday")
    assert "Thursday" in card.close
    assert passes_tone_gate(card, decision=decision, note=note)


# =============================================================================
# AC — ~4 lines / ~10s; passes the human-tutor gate
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_card_is_about_four_lines_and_passes_gate(name, factory, flavor, trust) -> None:
    card, decision, note = _compose(factory)
    lines = [ln for ln in card.text.splitlines() if ln.strip()]
    assert len(lines) == 4  # catch / why / move / celebrate+close
    assert len(lines) <= MAX_CARD_LINES
    assert len(card.text) <= MAX_CARD_CHARS
    # The five parts are all present in the rendered text.
    assert card.catch in card.text
    assert card.why_it_matters in card.text
    assert card.move in card.text
    assert card.on_his_side in card.text
    assert card.close in card.text
    # And it passes its own human-tutor gate.
    assert passes_tone_gate(card, decision=decision, note=note)
    assert tone_gate_violations(card, decision=decision, note=note) == []


# =============================================================================
# AC — trust-aware degradation
# =============================================================================


def test_grounded_cites_the_exact_label() -> None:
    """grounded → the EXACT anchor label + source/page, verbatim in the citation & move."""
    card, decision, note = _compose(abandonment_grounded)
    assert card.trust_level == "grounded"
    label = decision.grounded_anchor.label
    assert label == "Problem 11.1"
    assert label in card.citation
    assert card.citation == "Problem 11.1 (Tu, p.142)"
    assert card.citation in card.move


def test_section_grounded_degrades_to_the_section_no_fake_number() -> None:
    """section-grounded → the section (heading_path), NO fabricated exercise number."""
    import re

    for factory in (unverified_proof_section, abandonment_section):
        card, decision, note = _compose(factory)
        assert card.trust_level == "section-grounded"
        # No exact label was invented (the anchor carries none).
        assert decision.grounded_anchor.label is None
        # The citation degrades to the § section, carries no exercise coordinate.
        assert card.citation.startswith("§")
        fabricated = re.compile(r"\b(problem|exercise|prob|ex|lemma|proposition|corollary)\.?\s*\d", re.I)
        assert not fabricated.search(card.citation)
        assert not fabricated.search(card.move)


def test_unverified_proof_section_cites_the_ift_section() -> None:
    card, decision, note = _compose(unverified_proof_section)
    assert card.citation == "§8 The Inverse Function Theorem (Tu, p.90)"


def test_ungrounded_decision_is_refused_never_invents_a_number() -> None:
    """A fired decision carrying an ungrounded anchor is a #70 contract violation:
    compose REFUSES (ValueError) rather than fabricate a coordinate."""
    ungrounded = GroundedAnchor(
        book_id=BOOK_ID,
        node_id=None,
        label=None,
        page=None,
        heading_path=[],
        source=None,
        score=None,
        query="off-book",
        trust_level="ungrounded",
        matched=False,
    )
    signal = CandidateSignal(
        kind="abandoned_crux",
        verbatim_quote="assume it and move on",
        topic="an off-book trick",
        written_coordinate=None,
        source_note_date=D28,
        grounded_anchor=ungrounded,
    )
    decision = MentorDecision(
        fire=True,
        kind="repair",
        winning_signal=signal,
        grounded_anchor=ungrounded,
        quote="assume it and move on",
        suppressed=[],
        reason="synthetic contract violation",
    )
    note = NoteView(date=D28, markdown="## x", transcript="assume it and move on")
    with pytest.raises(ValueError, match="ungrounded"):
        compose_repair_card(decision, note, build_card_writer())


def test_render_citation_refuses_ungrounded_directly() -> None:
    ungrounded = GroundedAnchor(
        book_id=BOOK_ID, node_id=None, label=None, page=None, heading_path=[],
        source=None, score=None, query="q", trust_level="ungrounded", matched=False,
    )
    with pytest.raises(ValueError):
        render_citation(ungrounded)


def test_render_citation_uses_only_anchor_fields() -> None:
    """The citation is a pure function of the anchor's fields — nothing invented."""
    grounded = GroundedAnchor(
        book_id="Tu", node_id="n", label="Problem 2.16", page=24, heading_path=["Ch", "§1.2"],
        source="src", score=0.8, query="q", trust_level="grounded", matched=True,
    )
    assert render_citation(grounded) == "Problem 2.16 (Tu, p.24)"
    # Drop the page → it falls out of the citation (nothing fabricated to fill it).
    no_page = grounded.model_copy(update={"page": None})
    assert render_citation(no_page) == "Problem 2.16 (Tu)"
    # section-grounded degrades to the deepest § breadcrumb, label stays out.
    section = GroundedAnchor(
        book_id="Tu", node_id=None, label=None, page=100, heading_path=["Chapter 2", "§9 The RLS Theorem"],
        source="s", score=0.7, query="q", trust_level="section-grounded", matched=True,
    )
    assert render_citation(section) == "§9 The RLS Theorem (Tu, p.100)"


# =============================================================================
# compose refuses ill-formed decisions (hands back to #70)
# =============================================================================


def test_compose_refuses_a_non_firing_decision() -> None:
    retrieve = build_retrieve()
    silent = arbitrate([], note=NoteView(date=D28), retrieve=retrieve)
    assert silent.fire is False
    with pytest.raises(ValueError, match="FIRED"):
        compose_repair_card(silent, NoteView(date=D28), build_card_writer())


def test_compose_refuses_a_bridge_decision() -> None:
    """A `kind='bridge'` decision is not this module's to compose."""
    notes, retrieve, extractor, book_id = build_corpus()
    decisions = drive_corpus(notes, retrieve, extractor, book_id=book_id, cues=build_cues())
    by_date = {n.date: d for n, d in zip(sorted(notes, key=lambda n: n.date), decisions)}
    bridge = by_date[D27]
    assert bridge.fire is True and bridge.kind == "bridge"
    note = next(n for n in notes if n.date == D27)
    with pytest.raises(ValueError, match="repair"):
        compose_repair_card(bridge, note, build_card_writer())


def test_compose_refuses_a_note_from_a_different_day() -> None:
    decision, note = abandonment_grounded()
    wrong_note = NoteView(date="2025-01-01", markdown="unrelated")
    with pytest.raises(ValueError, match="same note"):
        compose_repair_card(decision, wrong_note, build_card_writer())


# =============================================================================
# The tone / human-tutor gate as a validator (rejects bad cards)
# =============================================================================


def _good_card() -> tuple[MentorCard, MentorDecision, NoteView]:
    return _compose(abandonment_grounded)


def test_gate_passes_a_well_formed_card() -> None:
    card, decision, note = _good_card()
    assert passes_tone_gate(card, decision=decision, note=note) is True
    assert_tone_gate(card, decision=decision, note=note)  # does not raise


def test_gate_rejects_a_non_verbatim_catch() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"catch": "He seemed unsure about the proof."})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert not passes_tone_gate(bad, decision=decision, note=note)
    assert any("verbatim" in v for v in violations)


def test_gate_rejects_a_topic_only_move() -> None:
    card, decision, note = _good_card()
    topic = decision.winning_signal.topic
    bad = card.model_copy(update={"move": f"{topic} {card.citation}"})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert not passes_tone_gate(bad, decision=decision, note=note)
    assert any("topic" in v or "verb" in v for v in violations)


def test_gate_rejects_a_move_with_no_citation() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"move": "Redo the whole thing from scratch."})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert any("anchored" in v for v in violations)


def test_gate_rejects_a_move_that_gives_the_answer() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"move": f"{card.move} By the way, the answer is 42."})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert any("answer" in v for v in violations)


def test_gate_rejects_a_multiline_why() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"why_it_matters": "First line.\nSecond line."})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert any("one line" in v for v in violations)


def test_gate_rejects_generic_praise() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"on_his_side": "Great work, keep it up!"})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert any("generic" in v or "same note" in v for v in violations)


def test_gate_rejects_a_missing_when() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"close": "I'll follow up at some point."})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert any("concrete when" in v for v in violations)


def test_gate_rejects_grade_and_hedge_language() -> None:
    card, decision, note = _good_card()
    graded = card.model_copy(update={"why_it_matters": "Solid effort — I'd grade this a B+."})
    assert any("tell" in v for v in tone_gate_violations(graded, decision=decision, note=note))
    hedged = card.model_copy(update={"move": f"If you'd like, {card.move}"})
    assert any("tell" in v for v in tone_gate_violations(hedged, decision=decision, note=note))


def test_gate_rejects_a_card_too_long_to_glance() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"text": "\n".join([card.text] * 4)})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert any("lines" in v or "chars" in v for v in violations)


def test_gate_rejects_a_fabricated_number_on_a_section_grounded_card() -> None:
    """The hard rule, gated: a section-grounded card must never smuggle in an
    exercise number the anchor didn't carry."""
    card, decision, note = _compose(unverified_proof_section)
    assert card.trust_level == "section-grounded"
    bad = card.model_copy(update={"move": f"{card.move} — specifically Problem 9.9"})
    violations = tone_gate_violations(bad, decision=decision, note=note)
    assert any("fabricated" in v for v in violations)


def test_assert_tone_gate_raises_with_violations() -> None:
    card, decision, note = _good_card()
    bad = card.model_copy(update={"close": "later"})
    with pytest.raises(ToneGateError) as exc:
        assert_tone_gate(bad, decision=decision, note=note)
    assert exc.value.violations
    assert any("concrete when" in v for v in exc.value.violations)


# =============================================================================
# The MentorCard contract + the CardWriter seam
# =============================================================================


def test_mentor_card_shape_and_extra_forbid() -> None:
    assert set(MentorCard.model_fields) == {
        "flavor", "catch", "why_it_matters", "move", "close",
        "on_his_side", "citation", "trust_level", "source_note_date", "text",
    }
    with pytest.raises(ValidationError):
        MentorCard(  # type: ignore[call-arg]
            flavor="abandonment", catch="c", why_it_matters="w", move="m",
            close="Sunday", on_his_side="o", citation="x", trust_level="grounded",
            source_note_date=D28, text="t", nope=1,
        )


def test_seeded_writer_satisfies_the_protocol() -> None:
    assert isinstance(build_card_writer(), CardWriter)
    assert isinstance(SeededCardWriter(), CardWriter)


# =============================================================================
# The hard rule: compose does NO retrieval of its own (no re-resolution)
# =============================================================================


class _RecordingRetrieve:
    """Wraps the seeded port and counts calls, to prove compose never retrieves."""

    def __init__(self) -> None:
        self._inner = build_retrieve()
        self.calls: list[BookRetrieveInput] = []

    def __call__(self, req: BookRetrieveInput):
        self.calls.append(req)
        return self._inner(req)


def test_compose_touches_the_book_zero_times() -> None:
    """All grounding happened upstream (#68/#70); compose only renders the anchor
    it was handed — it makes NO retrieval, no re-resolution, no OCR."""
    retrieve = _RecordingRetrieve()
    note = build_unverified_proof_note()
    cand = make_candidate(
        "unverified_proof",
        "the inverse function theorem",
        retrieve=retrieve,
        date=D27,
        quote="I'm honestly not sure the estimate is tight — moving on",
    )
    decision = _fire(cand, note, retrieve)
    calls_before = len(retrieve.calls)
    card = compose_repair_card(decision, note, build_card_writer())
    assert len(retrieve.calls) == calls_before  # compose added zero retrievals
    assert card.citation == "§8 The Inverse Function Theorem (Tu, p.90)"


# =============================================================================
# Determinism
# =============================================================================


@pytest.mark.parametrize("name,factory,flavor,trust", SCENARIOS, ids=_IDS)
def test_compose_is_deterministic(name, factory, flavor, trust) -> None:
    decision, note = factory()
    writer = build_card_writer()
    a = compose_repair_card(decision, note, writer)
    b = compose_repair_card(decision, note, writer)
    assert a == b


def test_writer_falls_back_when_unseeded_and_still_passes_the_gate() -> None:
    """An unseeded topic uses the writer's note-grounded fallbacks — which still
    produce a card that passes the human-tutor gate (the seam is safe by default)."""
    retrieve = build_retrieve()
    note = NoteView(
        date=D24,
        density_tier="standard",
        markdown="## Diagonalization\nAssumed the symmetric matrix diagonalizes; skipped the details.",
        transcript="I'll just assume I can diagonalize it and keep going.",
    )
    cand = make_candidate(
        "abandoned_crux",
        "diagonalizing a symmetric matrix",  # no override in build_card_writer
        retrieve=retrieve,
        date=D24,
        quote="I'll just assume I can diagonalize it and keep going.",
    )
    decision = _fire(cand, note, retrieve)
    card = compose_repair_card(decision, note, build_card_writer())
    assert passes_tone_gate(card, decision=decision, note=note)

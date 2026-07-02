"""Restraint & arbitration (issue #70) — the IF and the WHICH → `MentorDecision`.

Detection (#69) emits a *set* of grounded `CandidateSignal`s; this module makes
the one call detection deliberately refused to make: **does a card fire tonight,
and which one?** The governing principle is asymmetric — *a wrong card is
strictly worse than a missed one* (a miss costs one opportunity; a wrong card
costs the instrument). So **the default is silence**, and every gate below is a
reason to *stay* silent.

Like #68/#69 this is **engine-free, deterministic, pydantic-only** — it makes
**no** model call. Two things are genuinely LLM-shaped and both are injected, not
inlined:

  * **Grounding** rides *only* through #68's `resolve_anchor` (the injected
    `BookRetrieveFn`). The adversarial self-check re-resolves the winning
    candidate's anchor to confirm it *still names a real skeleton unit* before
    firing — there is **no** independent retrieval path (no SQL/OCR/vector store).
  * **Verbal cues** (reading "kind of distracted" as a light/low-signal night, or
    that a concern was raised *and self-closed* within one note) ride on a small
    injectable `NightCueReader` seam — exactly like `SignalExtractor`. The policy
    around it is deterministic and unit-testable with an in-memory fake.

The pieces:

  * `MentorDecision` — the output contract, handed to #71 (repair) / bridge cards
    **only when `fire=True`**.
  * `arbitrate(candidates, *, note, retrieve, history, cues)` — the **per-night**
    decision: anti-pattern silences → confidence bar → adversarial self-check →
    one-card-max arbitration (live repair > ripe bridge) → corpus-cap backstop.
  * `drive_corpus(...)` — the **corpus-level** driver: walks the notes in date
    order threading `MentorState` (cards fired so far, the consecutive-ignore
    streak) so corpus-wide restraint (≤2 cards, back off on repeated ignores)
    emerges from the per-night calls.

The confidence bar is deliberately a tiny, transparent, tunable function of the
three inputs the epic names — **anchor trust + `density_tier` + verbal cue** —
plus the ignore streak. The exact numbers are an open seam (#55 calibration);
what matters is the *ordering* they induce and that the bar only ever **rises**
(backs off), never falls (never escalates).
"""
from __future__ import annotations

from typing import Literal, Optional, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from mathai.math_mentor.anchor import GroundedAnchor, TrustLevel, resolve_anchor
from mathai.math_mentor.detection import (
    DensityTier,
    NoteView,
    detect_candidates,
    trailing_window,
)
from mathai.math_mentor.port import BookRetrieveFn
from mathai.math_mentor.signals import (
    CandidateKind,
    CandidateSignal,
    SignalExtractor,
    intent_for_kind,
)

# --- tunables (open seam: "Score/trust → confidence-bar mapping"; #55) ---------

#: Corpus-wide card budget — at most this many cards fire across the whole note
#: window. A backstop enforced by `arbitrate` via `history.cards_fired`; in the
#: canonical corpus the anti-pattern silences already hold the count at/under it,
#: but the cap guarantees restraint even if calibration drifts.
MAX_CORPUS_CARDS = 2

#: The base confidence a candidate must clear to fire on a *fresh* night (no
#: ignore streak). Chosen so a ``section-grounded`` candidate on a ``standard``
#: night just clears it, while the same candidate on a ``brief`` night does not —
#: i.e. weak-anchor + light-night falls below the bar (the epic's example).
BASE_BAR = 0.55

#: How much each *consecutive ignored card* raises the bar. Strictly positive so
#: the bar only ever rises on repeated ignores (backs off) — never falls (never
#: escalates). A landed card (fired and not ignored) resets the streak to 0.
IGNORE_STEP = 0.15

#: Anchor trust → base confidence. ``grounded`` (an exact coordinate-label match)
#: is the strongest possible signal; ``section-grounded`` is real but weaker;
#: ``ungrounded`` cannot contribute a firing card at all (and never reaches here —
#: #69 drops it, and the self-check re-confirms).
TRUST_CONFIDENCE: dict[TrustLevel, float] = {
    "grounded": 1.0,
    "section-grounded": 0.6,
    "ungrounded": 0.0,
}

#: `density_tier` → a *small* additive modifier. Context, not a trigger: a light
#: (``brief``) night nudges confidence down, a ``deep`` night nudges it up, but
#: density alone never fires or silences a card — the verbal cue does that.
DENSITY_MODIFIER: dict[DensityTier, float] = {
    "brief": -0.15,
    "standard": 0.0,
    "deep": 0.05,
}


# --- cross-night state --------------------------------------------------------


class MentorState(BaseModel):
    """The state the corpus-level driver threads across nights.

    Immutable-by-convention: the driver builds a *fresh* `MentorState` after each
    firing night rather than mutating in place, so the per-night `arbitrate` only
    ever *reads* it. Two counters do the work of corpus-wide restraint:

      * `cards_fired` — total cards fired so far (feeds the ``≤2`` corpus cap).
      * `consecutive_ignores` — the length of the current run of *fired-then-
        ignored* cards. It raises the confidence bar (backoff); a card that lands
        (fires and is **not** ignored) resets it to 0. Silence does not touch it —
        only an actually-fired card can be ignored.

    `fired_dates` is carried for inspection/tests (which nights produced a card).
    """

    model_config = ConfigDict(extra="forbid")

    cards_fired: int = Field(0, ge=0, description="Total cards fired so far (drives the ≤2 corpus cap).")
    consecutive_ignores: int = Field(
        0, ge=0, description="Length of the current fired-then-ignored streak (raises the bar)."
    )
    fired_dates: list[str] = Field(default_factory=list, description="Dates a card fired on (inspection).")


# --- the verbal-cue seam (LLM-shaped, injected — never a model call here) ------


class NightCue(BaseModel):
    """A read of a night's *disposition cues* — the verbal-cue seam's output.

    What a model reading the whole note *would* conclude about the learner's
    state, captured as deterministic flags so the policy stays testable:

      * `distracted` — a light / low-signal verbal cue ("short one today, kind of
        distracted"). The epic insists this is read from the **transcript cue**,
        not inferred from `density_tier` — a brief night with a real hedge still
        fires, a distracted night does not.
      * `self_closed_topics` — topics the learner both *raised and closed within
        the same note*. A repair candidate whose topic self-closed the same day is
        **stale**: the prerequisite is already shored up, so firing a card for it
        would be a wrong card. Matched against a candidate's `topic`
        case-insensitively.
    """

    model_config = ConfigDict(extra="forbid")

    distracted: bool = Field(
        False, description="Light/low-signal verbal cue (e.g. 'kind of distracted') — suppresses the night."
    )
    self_closed_topics: list[str] = Field(
        default_factory=list,
        description="Topics raised AND closed within the same note (stale → their repair candidate drops).",
    )


@runtime_checkable
class NightCueReader(Protocol):
    """The injectable seam that reads a `NoteView` into a `NightCue`.

    Production injects a Claude-backed reader; tests inject an in-memory fake
    seeded per date (see `tests/corpus.py::build_cues`). `arbitrate` calls it at
    most once per night and never calls a model itself. `runtime_checkable` so a
    fake can be `isinstance`-asserted against the port.
    """

    def read(self, note: NoteView) -> NightCue:  # noqa: D401
        ...


# --- the output contract ------------------------------------------------------


DecisionKind = Literal["repair", "bridge", "none"]


class MentorDecision(BaseModel):
    """The per-night verdict — the #70 output contract.

    Handed to #71 (repair card) / the bridge card **only when `fire=True`**. When
    `fire=False` everything decision-shaped is null and `kind="none"`, but the
    `suppressed` list still carries **every** candidate that surfaced — losers are
    *preserved*, never discarded, so a later pass (or #56 cooldown) can reconsider
    them.

    `kind` maps from the winning candidate's kind:
    ``abandoned_crux``/``unverified_proof`` → ``"repair"``; ``ripe_bridge`` →
    ``"bridge"``; nothing fires → ``"none"``. When `fire=True` the invariants the
    ACs demand hold: `quote` is a non-empty verbatim span and `grounded_anchor` is
    **never `ungrounded`** (it is the anchor re-confirmed by the self-check).
    """

    model_config = ConfigDict(extra="forbid")

    fire: bool = Field(..., description="Whether a card fires tonight (default posture is False).")
    kind: DecisionKind = Field(..., description="repair | bridge | none (from the winning candidate's kind).")
    winning_signal: Optional[CandidateSignal] = Field(
        None, description="The candidate that won arbitration (None iff no card fires)."
    )
    grounded_anchor: Optional[GroundedAnchor] = Field(
        None, description="The self-check-re-confirmed anchor for the winner — never ungrounded when firing."
    )
    quote: Optional[str] = Field(
        None, description="The winner's verbatim transcript quote (None iff no card fires)."
    )
    suppressed: list[CandidateSignal] = Field(
        default_factory=list, description="Every non-winning candidate this night — preserved, not discarded."
    )
    reason: str = Field(..., description="Human-readable rationale for the fire/silence decision.")


# --- confidence primitives (pure, directly unit-testable) ---------------------


def _is_repair(kind: CandidateKind) -> bool:
    """A *live repair* signal (abandoned crux / unverified proof) vs a connect (bridge)."""
    return kind in ("abandoned_crux", "unverified_proof")


def _norm_topic(topic: str) -> str:
    """Normalize a topic for self-closed matching (case/space-insensitive)."""
    return " ".join(topic.strip().lower().split())


def candidate_confidence(candidate: CandidateSignal, note: NoteView) -> float:
    """Confidence in a candidate, in ``[0, 1]``, from **anchor trust + density_tier**.

    The verbal cue (distracted / self-closed) is applied as a *gate* upstream, not
    folded in here — this function is the trust×density component of the bar the
    epic names. Deterministic and monotone in trust: a ``grounded`` anchor always
    scores above a ``section-grounded`` one at equal density.
    """
    base = TRUST_CONFIDENCE[candidate.grounded_anchor.trust_level]
    modifier = DENSITY_MODIFIER[note.density_tier]
    return max(0.0, min(1.0, base + modifier))


def confidence_bar(consecutive_ignores: int) -> float:
    """The bar a candidate must clear tonight, given the current ignore streak.

    ``BASE_BAR + IGNORE_STEP * consecutive_ignores`` — a non-decreasing function
    of the streak. On repeated ignores the mentor **backs off** (the bar rises, so
    fewer/only-stronger cards clear); it **never escalates** (the bar never falls
    below `BASE_BAR`). A landed card resets the streak (see `MentorState`).
    """
    return BASE_BAR + IGNORE_STEP * max(0, consecutive_ignores)


# --- the per-night decision ---------------------------------------------------


def _silent(candidates: Sequence[CandidateSignal], reason: str) -> MentorDecision:
    """A silence verdict that still *preserves* every candidate in `suppressed`."""
    return MentorDecision(
        fire=False,
        kind="none",
        winning_signal=None,
        grounded_anchor=None,
        quote=None,
        suppressed=list(candidates),
        reason=reason,
    )


def arbitrate(
    candidates: Sequence[CandidateSignal],
    *,
    note: NoteView,
    retrieve: BookRetrieveFn,
    history: Optional[MentorState] = None,
    cues: Optional[NightCueReader] = None,
) -> MentorDecision:
    """Decide whether — and which — card fires for one night. Default: silence.

    The gate order (each is a reason to stay silent):

      0. **No candidates** → silence.
      1. **`dont_spoil` flair** → respect the learner's deliberate in-progress
         work; suppress the whole night.
      2. **Distracted verbal cue** → a light/low-signal night (read from the cue,
         *not* `density_tier`); suppress the whole night.
      3. **Staleness** → drop any candidate whose topic was *self-closed the same
         day* (a prerequisite already shored up is not a live crux).
      4. **Confidence bar** → drop any candidate whose ``trust×density``
         confidence falls below `confidence_bar(streak)` (weak anchor on a light
         or repeatedly-ignored night does not clear it).
      5. **One-card-max arbitration** → among survivors, **live repair > ripe
         bridge** (ties broken by confidence, then date/topic for determinism).
      6. **Adversarial self-check** → re-resolve the winner's anchor through #68's
         `resolve_anchor`; if it comes back ``ungrounded`` it cannot fire (we
         won't point at a card we can no longer ground).
      7. **Corpus-cap backstop** → if the budget (`history.cards_fired`) is spent,
         stay silent.

    Grounding rides **only** through `resolve_anchor(retrieve, …)` — no
    independent retrieval. `cues` and `history` are injected; both default to a
    neutral value so `arbitrate` is usable stand-alone.
    """
    history = history or MentorState()
    all_candidates = list(candidates)

    # 0. Default silence when there is nothing to decide.
    if not all_candidates:
        return _silent(all_candidates, "no candidate surfaced tonight — default silence")

    cue = cues.read(note) if cues is not None else NightCue()

    # 1. Respect the dont_spoil flair — the learner asked us not to reveal the finish.
    if note.dont_spoil:
        return _silent(
            all_candidates,
            "deliberate in-progress note (dont_spoil flair) — respecting the learner's own work",
        )

    # 2. Distracted / light night — read the VERBAL CUE, not density_tier.
    if cue.distracted:
        return _silent(
            all_candidates,
            "distracted / light night (verbal cue) — not the moment for a card",
        )

    # 3-4. Per-candidate gates: staleness (self-closed) then the confidence bar.
    self_closed = {_norm_topic(t) for t in cue.self_closed_topics}
    bar = confidence_bar(history.consecutive_ignores)

    stale_dropped: list[CandidateSignal] = []
    below_bar_dropped: list[CandidateSignal] = []
    survivors: list[CandidateSignal] = []
    for c in all_candidates:
        if _norm_topic(c.topic) in self_closed:
            stale_dropped.append(c)  # self-closed the same day → stale
            continue
        if candidate_confidence(c, note) < bar:
            below_bar_dropped.append(c)  # weak anchor / light / ignored-streak night
            continue
        survivors.append(c)

    if not survivors:
        if stale_dropped and not below_bar_dropped:
            reason = "stale — every candidate's topic was self-closed the same day"
        elif below_bar_dropped and not stale_dropped:
            reason = f"below the confidence bar ({bar:.2f}) — weak anchor on a low-signal/ignored night"
        else:
            reason = (
                f"no candidate cleared the bar ({bar:.2f}): "
                f"{len(stale_dropped)} stale, {len(below_bar_dropped)} below-bar"
            )
        return _silent(all_candidates, reason)

    # 5. One-card-max arbitration: live repair beats ripe bridge. Deterministic.
    survivors.sort(
        key=lambda c: (
            0 if _is_repair(c.kind) else 1,
            -candidate_confidence(c, note),
            c.source_note_date,
            c.topic,
        )
    )
    winner = survivors[0]

    # 6. Adversarial self-check: re-resolve the winner's anchor via #68 (the ONLY
    #    retrieval path). It must still name a real skeleton unit to fire.
    reresolved = resolve_anchor(
        retrieve,
        book_id=winner.grounded_anchor.book_id,
        coordinate=winner.written_coordinate,
        topic=winner.topic,
        intent=intent_for_kind(winner.kind),
    )
    if reresolved.trust_level == "ungrounded":
        return _silent(
            all_candidates,
            "adversarial self-check failed — the anchor no longer resolves to a real skeleton unit",
        )

    # 7. Corpus-cap backstop — the budget is spent, stay silent (losers preserved).
    if history.cards_fired >= MAX_CORPUS_CARDS:
        return _silent(
            all_candidates,
            f"corpus card budget exhausted ({history.cards_fired}/{MAX_CORPUS_CARDS}) — staying silent",
        )

    # FIRE. The winner leaves; every other candidate is preserved in `suppressed`.
    decision_kind: DecisionKind = "repair" if _is_repair(winner.kind) else "bridge"
    conf = candidate_confidence(winner, note)
    suppressed = [c for c in all_candidates if c is not winner]
    return MentorDecision(
        fire=True,
        kind=decision_kind,
        winning_signal=winner,
        grounded_anchor=reresolved,
        quote=winner.verbatim_quote,
        suppressed=suppressed,
        reason=(
            f"fires ({decision_kind}): {winner.kind} cleared the bar "
            f"(confidence {conf:.2f} ≥ {bar:.2f}, trust={reresolved.trust_level}); "
            f"self-check re-confirmed the anchor; "
            f"{len(suppressed)} candidate(s) preserved"
        ),
    )


# --- the corpus-level driver --------------------------------------------------


def drive_corpus(
    notes: Sequence[NoteView],
    retrieve: BookRetrieveFn,
    extractor: SignalExtractor,
    *,
    book_id: str,
    cues: Optional[NightCueReader] = None,
    ignored_dates: Optional[set[str]] = None,
    window: Optional[int] = None,
) -> list[MentorDecision]:
    """Walk the note window in date order, threading state → a decision per night.

    Corpus-wide restraint *emerges* from the per-night `arbitrate` calls plus the
    threaded `MentorState`:

      * **≤ `MAX_CORPUS_CARDS` across the corpus** — each fire increments
        `cards_fired`; once the budget is spent `arbitrate` refuses to fire.
      * **Back off on repeated ignores** — `ignored_dates` models the learner's
        feedback: the set of note-dates whose *fired* card was subsequently
        ignored. (Chosen representation: a set of dates — inspectable, order-free,
        and only meaningful for dates a card actually fired on.) When a fired
        card's date is in the set the consecutive-ignore streak grows and the bar
        rises for later nights; a card that lands resets the streak. Silence never
        counts as an ignore (only a fired card can be ignored).

    Candidates are produced once by #69's `detect_candidates` (the ONLY detection
    path) and bucketed by `source_note_date`; each night sees exactly the
    candidates that surfaced from its own note. Returns one `MentorDecision` per
    note in the window, in date order.
    """
    ignored = set(ignored_dates or ())
    windowed = trailing_window(notes, window)

    candidates = detect_candidates(notes, retrieve, extractor, book_id=book_id, window=window)
    by_date: dict[str, list[CandidateSignal]] = {}
    for c in candidates:
        by_date.setdefault(c.source_note_date, []).append(c)

    state = MentorState()
    decisions: list[MentorDecision] = []
    for note in windowed:
        tonight = by_date.get(note.date, [])
        decision = arbitrate(tonight, note=note, retrieve=retrieve, history=state, cues=cues)
        decisions.append(decision)
        if decision.fire:
            if note.date in ignored:
                streak = state.consecutive_ignores + 1  # fired then ignored → back off
            else:
                streak = 0  # a card that landed resets the streak
            state = MentorState(
                cards_fired=state.cards_fired + 1,
                consecutive_ignores=streak,
                fired_dates=[*state.fired_dates, note.date],
            )
        # A silent night leaves the state (and the ignore streak) untouched.
    return decisions

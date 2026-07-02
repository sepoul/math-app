"""Repair card compose + tone gate (issue #71) — content, shape, tone.

Given a **fired** ``MentorDecision{kind:"repair"}`` (from #70) and its
``GroundedAnchor`` (resolved via #68's ``book_retrieve`` seam), compose **one**
repair card. This module owns the *content, shape, and tone* of the directive —
**not** the decision to fire (that is #70). Two flavors of the same shape:

  * ``abandonment``       — the learner dropped a crux (``abandoned_crux``).
  * ``unverified_proof``  — the learner wrote a proof he never checked.

Like #68/#69/#70 this is **engine-free, deterministic, pydantic-only** — it
makes **no** model call. The three genuinely generative bits are LLM-shaped and
injected behind the `CardWriter` seam (exactly like #69's `SignalExtractor` /
#70's `NightCueReader`), never inlined:

  1. **why-it-matters** — the one-line crux-vs-bookkeeping rationale;
  2. **the move phrasing** — the verb + the specific step (never the citation);
  3. **the celebration** — selecting one *specific real win* from the same note.

Everything else is deterministic and lives here:

  * the **assembly** of the five parts into a ``MentorCard``;
  * the **trust-aware CITATION rendering** from the anchor (`render_citation`);
  * the **tone / human-tutor GATE** (`tone_gate_violations` / `passes_tone_gate`
    / `assert_tone_gate`) — the validator that asserts a composed card reads like
    something a real tutor would say.

The hard rule (non-negotiable). **The single move's anchor IS the
``GroundedAnchor`` the decision already carries.** The card NEVER invents a
coordinate: the citation is rendered *only* from the anchor's fields
(``label`` / ``source`` / ``page`` / ``heading_path``). No OCR, no SQL, no
re-retrieval, no fabricated exercise numbers. `compose_repair_card` does not call
`resolve_anchor` — the decision already carries the self-check-re-confirmed
anchor; this module only renders from it.

Trust-aware degradation.
  * ``grounded``          → cite the **exact** ``label`` (e.g. *"Problem 11.1
                            (Tu, p.142)"*).
  * ``section-grounded``  → **degrade** to the section (the ``heading_path`` /
                            ``§…``), with **no** fabricated exercise number.
  * ``ungrounded``        → a fired ``MentorDecision`` *guarantees* a
                            non-ungrounded anchor, so an ungrounded anchor here is
                            a **contract violation**: `compose_repair_card`
                            **refuses** (raises `ValueError`) and hands back to
                            #70. We never fabricate a number to fill the gap.

Because the platform's shipped ``dont_spoil`` guarantee means the move can be
maximally directive with zero spoiler risk, the card leans directive — reread /
redo / do / verify — while the gate keeps it from ever handing over the answer.
"""
from __future__ import annotations

import re
from typing import Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from mathai.math_mentor.anchor import GroundedAnchor, TrustLevel
from mathai.math_mentor.arbitration import MentorDecision
from mathai.math_mentor.detection import NoteView
from mathai.math_mentor.signals import CandidateKind

# --- flavor -------------------------------------------------------------------

#: The repair card's flavor — one shape, two variants, mapped 1:1 from the
#: winning candidate's kind. ``ripe_bridge`` is NOT a repair kind and never
#: reaches here (a bridge decision goes to the bridge card, not this module).
CardFlavor = Literal["abandonment", "unverified_proof"]

_FLAVOR_BY_KIND: dict[CandidateKind, CardFlavor] = {
    "abandoned_crux": "abandonment",
    "unverified_proof": "unverified_proof",
}


# --- gate tunables (bounds; provisional, tune with #55) -----------------------

#: Upper bound on the rendered card's line count — "~4 lines". A card that
#: assembles more than this reads as a wall of text, not a ~10s glance.
MAX_CARD_LINES = 6

#: Upper bound on the rendered card's character length — the "~10s to read"
#: budget. Generous headroom over the canonical ~400-char cards.
MAX_CARD_CHARS = 700

#: Upper bound on the one-line why-it-matters — a *line*, not a paragraph.
MAX_WHY_CHARS = 200

#: Directive verbs a real one-sitting move opens with (reread / redo / do /
#: verify and close cousins). A move must contain at least one — a card that
#: doesn't *direct* an action isn't a move.
_MOVE_VERBS = (
    "reread", "re-read", "redo", "re-do", "rederive", "re-derive", "rework",
    "re-work", "rebuild", "reprove", "re-prove", "revisit", "do ", "work",
    "verify", "check", "prove", "derive", "compute", "trace", "reconstruct",
    "fill in", "walk through", "write out",
)

#: Phrases that would hand over the answer — a move must never contain one. The
#: platform's shipped ``dont_spoil`` guarantee already makes spoilers unlikely;
#: this is the belt-and-braces gate over the composed text.
_SPOILER_PHRASES = (
    "the answer is", "the solution is", "here's the proof", "here is the proof",
    "the proof is:", "the result is", "q.e.d", "qed", "the value is",
)

#: Generic-praise phrases the on-his-side clause must NOT be — the clause has to
#: name a *specific real* thing from the note, not pat the learner on the head.
_GENERIC_PRAISE = (
    "good job", "great job", "great work", "good work", "nice work",
    "well done", "keep it up", "keep up the good work", "you're doing great",
    "you are doing great", "proud of you", "amazing work", "awesome",
)

#: Not-a-tutor tells — a real tutor states the move; they don't hedge it as an
#: option or slap a grade on it. Any of these fails the human-tutor gate.
_FORBIDDEN_TONE = (
    "if you'd like", "if you would like", "if you want", "if you feel like",
    "you could consider", "you might consider", "maybe you could",
    "perhaps you could", "grade", "score:", "out of 10", "out of ten",
    "/10", "a+", "b+", "rating", "well graded",
)

#: Concrete-when tokens — the close must name an actual time, not "later".
_WHEN_TOKENS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "today", "tonight", "tomorrow", "this week", "next week",
    "this weekend", "next session", "morning", "evening",
)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

#: A *fabricated* exercise-style coordinate (Problem / Exercise / Lemma … + a
#: number). Deliberately excludes ``§``, ``Section``, ``Chapter`` and a bare
#: ``Theorem`` (section titles legitimately read "… Theorem"): a section
#: citation degradation must NOT carry one of these, so on a ``section-grounded``
#: card the move is checked against this pattern.
_FABRICATED_COORD_RE = re.compile(
    r"\b(problems?|exercises?|exer|prob|ex|lemmas?|propositions?|prop|"
    r"corollar(?:y|ies)|cor|examples?)\.?\s*\d",
    re.IGNORECASE,
)


# --- the output contract ------------------------------------------------------


class MentorCard(BaseModel):
    """One composed repair card — the #71 output contract.

    Carries the **five parts** the anatomy names, plus the deterministically
    rendered ``citation`` and the ~4-line ``text`` a surface (the #54 loop-close)
    would show. ``extra="forbid"``: the shape is closed.

    Invariants a card that survives `compose_repair_card` guarantees (the gate
    enforces them):

      * ``catch`` is the learner's **verbatim** quote (``== decision.quote``);
      * ``citation`` is rendered **only** from the anchor — an exact ``label`` on
        ``grounded``, a **section** (no fabricated number) on ``section-grounded``;
      * ``move`` is **exactly one** book-anchored directive (it contains the
        ``citation``), doable in one sitting, never the answer;
      * ``on_his_side`` names one **specific real** thing from the same note;
      * ``close`` names a **concrete when**;
      * ``text`` is ~4 lines / ~10s and passes the human-tutor gate.
    """

    model_config = ConfigDict(extra="forbid")

    flavor: CardFlavor = Field(..., description="abandonment | unverified_proof (from the winner's kind).")
    # 1. The catch — in his words.
    catch: str = Field(..., description="The learner's verbatim quote (== decision.quote).")
    # 2. Why it matters — one line.
    why_it_matters: str = Field(..., description="One line: crux vs bookkeeping, a mathematician would sign it.")
    # 3. One book-rooted move — anchored to the GroundedAnchor.
    move: str = Field(..., description="EXACTLY ONE move (contains the rendered citation), one sitting, never the answer.")
    # 4. The close — a concrete when.
    close: str = Field(..., description="A concrete WHEN ('I'll ask you about it on Sunday').")
    # 5. On-his-side clause — one specific real win from the same note.
    on_his_side: str = Field(..., description="One SPECIFIC REAL win pulled from the same note (not generic praise).")
    # Rendered-from-the-anchor citation + provenance.
    citation: str = Field(..., description="Trust-aware citation rendered ONLY from the anchor's fields.")
    trust_level: TrustLevel = Field(..., description="The anchor's trust level — grounded | section-grounded.")
    source_note_date: str = Field(..., description="Date (YYYY-MM-DD) of the note this card repairs.")
    # The assembled ~4-line card.
    text: str = Field(..., description="The rendered ~4-line card (readable in ~10s).")


# --- the generative seam (LLM-shaped, injected — never a model call here) ------


@runtime_checkable
class CardWriter(Protocol):
    """The injectable seam for the card's three *generative* strings.

    Production injects a Claude-backed writer; tests inject an in-memory fake
    (see `tests/corpus.py::build_card_writer`). `compose_repair_card` calls each
    method at most once and never calls a model itself. The deterministic policy
    around the seam — assembly, the trust-aware citation, the tone gate — stays
    here and is fully unit-testable with the fake. `runtime_checkable` so a fake
    can be `isinstance`-asserted against the port.

    Each method receives the fired ``decision`` (with its ``winning_signal`` and
    re-confirmed ``grounded_anchor``) and the source ``note``:

      * `why_it_matters` → the ONE-line crux-vs-bookkeeping rationale.
      * `phrase_move` → the move's **action** (verb + the specific step). It must
        **NOT** include the citation — the deterministic assembler appends the
        anchor-rendered citation, so the writer physically cannot invent a
        coordinate. The verb it chooses SHOULD respect the anchor's trust
        (reread a section vs. redo an exact problem).
      * `celebrate` → one **specific real** win pulled from the same note's
        ``markdown`` / ``transcript`` (not generic praise).
    """

    def why_it_matters(self, decision: MentorDecision, note: NoteView) -> str:  # noqa: D401
        ...

    def phrase_move(self, decision: MentorDecision, note: NoteView) -> str:  # noqa: D401
        ...

    def celebrate(self, decision: MentorDecision, note: NoteView) -> str:  # noqa: D401
        ...


# --- trust-aware citation rendering (deterministic; the hard rule) ------------


def _section_ref(heading_path: list[str]) -> str:
    """Pick the deepest *section-naming* breadcrumb from a heading path.

    Prefers the deepest ``§…`` / ``Section …`` / ``Chapter …`` level (Tu's
    skeleton names sections ``§9 The Regular Level Set Theorem``); falls back to
    the deepest breadcrumb. Empty for an empty path.
    """
    for h in reversed(heading_path):
        s = h.strip()
        low = s.lower()
        if s.startswith("§") or low.startswith("section") or low.startswith("chapter"):
            return s
    return heading_path[-1].strip() if heading_path else ""


def render_citation(anchor: GroundedAnchor) -> str:
    """Render a citation **only** from the anchor's fields — trust-aware.

    The hard rule made concrete: the string is built from ``label`` / ``source``
    / ``page`` / ``heading_path`` — never fabricated, never re-retrieved.

      * ``grounded``          → the **exact** ``label`` + book (+ page):
                                ``"Problem 11.1 (Tu, p.142)"``.
      * ``section-grounded``  → **degrade** to the section (``§…`` / deepest
                                heading) + book (+ page), with **no** exercise
                                number: ``"§9 The Regular Level Set Theorem
                                (Tu, p.98)"``.
      * ``ungrounded``        → **refused** — a `ValueError` (a fired decision can
                                never carry one; see `compose_repair_card`).

    Raises `ValueError` on an ungrounded anchor, or a ``grounded`` anchor missing
    its ``label`` (that would be an internal #68 invariant violation — we refuse
    rather than invent).
    """
    if anchor.trust_level == "ungrounded":
        raise ValueError(
            "cannot render a citation for an ungrounded anchor — a fired repair "
            "decision must carry a grounded or section-grounded anchor"
        )

    book = anchor.book_id
    page = f", p.{anchor.page}" if anchor.page is not None else ""

    if anchor.trust_level == "grounded":
        if not (anchor.label and anchor.label.strip()):
            raise ValueError(
                "grounded anchor without a label — refusing to fabricate a coordinate"
            )
        return f"{anchor.label.strip()} ({book}{page})"

    # section-grounded → degrade to the section, NEVER a fabricated number.
    section = _section_ref(anchor.heading_path)
    if section:
        return f"{section} ({book}{page})"
    # No heading path to degrade to — lean on the anchor's pre-rendered source,
    # else the barest book(+page) pointer. Still never a fabricated coordinate.
    if anchor.source and anchor.source.strip():
        return anchor.source.strip()
    tail = page.lstrip(", ")
    return f"{book} ({tail})" if tail else book


# --- assembly (deterministic) -------------------------------------------------


def _assemble_move(action: str, citation: str, trust: TrustLevel) -> str:
    """Join the writer's action clause to the anchor-rendered citation.

    Deterministic and trust-shaped: on ``grounded`` the move *points* at the
    exact coordinate (``…, then Problem 11.1 (Tu, p.142).``); on
    ``section-grounded`` it degrades to the section (``… — §9 … (Tu, p.98).``).
    The citation is appended by the module, so the writer can never smuggle in a
    coordinate of its own.
    """
    action = action.strip().rstrip(" .;,—-")
    if trust == "grounded":
        return f"{action}, then {citation}."
    return f"{action} — {citation}."


def _render_text(catch: str, why: str, move: str, on_his_side: str, close: str) -> str:
    """Assemble the ~4-line card. His words first, then why → move → close."""
    return "\n".join(
        [
            f"“{catch}”",
            f"Why it matters: {why}",
            f"One move: {move}",
            f"{on_his_side} {close}",
        ]
    )


def compose_repair_card(
    decision: MentorDecision,
    note: NoteView,
    writer: CardWriter,
    *,
    check_in: str = "Sunday",
) -> MentorCard:
    """Compose ONE repair card from a fired repair decision + its anchor.

    Owns *content, shape, tone* — **not** the decision to fire. Preconditions
    (each a #70 contract the caller must have satisfied; a violation is refused
    with `ValueError`, never patched over):

      * ``decision.fire`` is ``True`` and ``decision.kind == "repair"``;
      * ``winning_signal`` and ``grounded_anchor`` are present;
      * the anchor is **not** ``ungrounded`` (a fired decision guarantees this —
        an ungrounded anchor here is a contract violation, handed back to #70);
      * ``note.date`` is the winner's ``source_note_date`` (the celebration must
        come from the **same** note).

    Then, deterministically: render the trust-aware citation from the anchor,
    ask the injected `writer` for the three generative strings, assemble the five
    parts + the ~4-line text, and **gate** the result — a card that fails the
    human-tutor gate raises `ToneGateError` (compose never returns a card that
    would not pass its own gate).
    """
    if not decision.fire:
        raise ValueError("compose_repair_card requires a FIRED decision (decision.fire is False)")
    if decision.kind != "repair":
        raise ValueError(f"compose_repair_card requires kind='repair', got {decision.kind!r}")
    signal = decision.winning_signal
    anchor = decision.grounded_anchor
    if signal is None or anchor is None:
        raise ValueError("a fired repair decision must carry a winning_signal and a grounded_anchor")
    if anchor.trust_level == "ungrounded":
        # The hard rule: never fabricate. A fired decision can't legitimately
        # carry an ungrounded anchor — refuse and hand back to #70.
        raise ValueError(
            "grounded_anchor is ungrounded — a repair card must never invent a "
            "coordinate; this is a #70 contract violation, not a card to compose"
        )
    if note.date != signal.source_note_date:
        raise ValueError(
            f"note.date ({note.date!r}) is not the winner's source_note_date "
            f"({signal.source_note_date!r}) — the celebration must come from the same note"
        )

    flavor = _FLAVOR_BY_KIND[signal.kind]

    # 1. The catch — his words, verbatim (carried on the decision).
    catch = decision.quote or signal.verbatim_quote

    # Deterministic, trust-aware citation — rendered ONLY from the anchor.
    citation = render_citation(anchor)

    # The three generative strings, from the injected seam.
    why = writer.why_it_matters(decision, note).strip()
    action = writer.phrase_move(decision, note).strip()
    on_his_side = writer.celebrate(decision, note).strip()

    # 3. One book-rooted move — the writer's action + the anchor citation.
    move = _assemble_move(action, citation, anchor.trust_level)

    # 4. The close — a concrete when (deterministic template).
    close = f"I'll ask you about it on {check_in}."

    text = _render_text(catch, why, move, on_his_side, close)

    card = MentorCard(
        flavor=flavor,
        catch=catch,
        why_it_matters=why,
        move=move,
        close=close,
        on_his_side=on_his_side,
        citation=citation,
        trust_level=anchor.trust_level,
        source_note_date=signal.source_note_date,
        text=text,
    )

    # Gate our own output — compose never returns a card that fails the gate.
    assert_tone_gate(card, decision=decision, note=note)
    return card


# --- the tone / human-tutor gate (deterministic validator) --------------------


class ToneGateError(ValueError):
    """Raised when a composed card fails the human-tutor gate.

    Carries the list of `violations` so callers (and #70, if it ever composes
    directly) can see exactly which tutor-voice invariant broke.
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("card failed the human-tutor gate: " + "; ".join(violations))


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _note_tokens_from_text(text: str) -> set[str]:
    """Substantive (len≥4, alphabetic) tokens of an arbitrary string."""
    return {t for t in re.findall(r"[a-z][a-z'-]{3,}", text.lower())}


def _note_tokens(note: NoteView) -> set[str]:
    """Substantive (len≥4, alphabetic) tokens across the note's markdown + transcript."""
    blob = " ".join(filter(None, [note.markdown or "", note.transcript or ""]))
    return _note_tokens_from_text(blob)


def tone_gate_violations(
    card: MentorCard,
    *,
    decision: MentorDecision,
    note: NoteView,
) -> list[str]:
    """Return the list of human-tutor-gate violations for a composed card (empty = passes).

    The gate asserts a real tutor would say *exactly this*. Each check maps to an
    acceptance criterion:

      * **quotes him** — ``catch`` equals the decision's verbatim quote, non-empty;
      * **specific step, not the topic** — the ``move`` names a step, isn't the
        bare topic, and carries a directive verb;
      * **one line why-it-matters** — single line, non-empty, bounded, that a
        mathematician would sign (no grade / hedge language);
      * **exactly one move, book-anchored, never the answer** — the ``move``
        contains the ``citation`` exactly once and no spoiler phrase;
      * **trust-aware citation** — ``grounded`` cites the exact anchor ``label``;
        ``section-grounded`` carries **no** fabricated exercise number;
      * **specific real celebration** — ``on_his_side`` is note-grounded (shares a
        substantive token with the note) and not generic praise;
      * **concrete when** — the ``close`` names an actual time;
      * **~4 lines / ~10s** — the ``text`` is within the line/char budget;
      * **never a grade, never "if you'd like…"** — no not-a-tutor tells anywhere.
    """
    v: list[str] = []
    signal = decision.winning_signal

    # --- quotes him ----------------------------------------------------------
    if not (card.catch and card.catch.strip()):
        v.append("the catch is empty — a card must quote him")
    elif decision.quote is not None and card.catch != decision.quote:
        v.append("the catch is not the learner's verbatim quote (catch != decision.quote)")

    # --- one-line why-it-matters ---------------------------------------------
    why = card.why_it_matters
    if not (why and why.strip()):
        v.append("why-it-matters is empty")
    else:
        if "\n" in why:
            v.append("why-it-matters is more than one line")
        if len(why) > MAX_WHY_CHARS:
            v.append(f"why-it-matters is too long ({len(why)} > {MAX_WHY_CHARS} chars) — it must be one line")

    # --- book-anchored, exactly one move, never the answer -------------------
    move = card.move
    move_low = move.lower()
    if not (card.citation and card.citation.strip()):
        v.append("citation is empty — the move must be book-anchored")
    elif card.citation not in move:
        v.append("the move is not anchored to the rendered citation")
    elif move.count(card.citation) != 1:
        v.append("the move carries more than one citation — a card fires exactly one move")
    if not any(verb in move_low for verb in _MOVE_VERBS):
        v.append("the move names no directive verb (reread / redo / do / verify …)")
    if any(sp in move_low for sp in _SPOILER_PHRASES):
        v.append("the move hands over the answer — it must direct, never solve")

    # --- names the specific step, not the topic ------------------------------
    if signal is not None:
        move_wo_cite = _norm(move.replace(card.citation, ""))
        if not move_wo_cite:
            v.append("the move is only a citation — it names no step")
        elif move_wo_cite == _norm(signal.topic):
            v.append("the move restates the topic — it must name the specific step")

    # --- trust-aware citation degradation ------------------------------------
    anchor = decision.grounded_anchor
    if card.trust_level == "grounded":
        label = (anchor.label if anchor else None) or ""
        if not label.strip():
            v.append("grounded card without an exact label")
        elif label not in card.citation:
            v.append("grounded card does not cite the anchor's exact label")
    elif card.trust_level == "section-grounded":
        if _FABRICATED_COORD_RE.search(card.citation):
            v.append("section-grounded card fabricated an exercise number in the citation")
        if _FABRICATED_COORD_RE.search(move):
            v.append("section-grounded card fabricated an exercise number in the move")
    else:  # ungrounded should never reach a MentorCard
        v.append(f"card carries a non-firing trust level ({card.trust_level!r})")

    # --- specific real celebration from the same note ------------------------
    win = card.on_his_side
    if not (win and win.strip()):
        v.append("the on-his-side clause is empty")
    else:
        win_low = win.lower()
        if any(p in win_low for p in _GENERIC_PRAISE):
            v.append("the celebration is generic praise, not a specific real win")
        if not (_note_tokens(note) & _note_tokens_from_text(win)):
            v.append("the celebration is not drawn from the same note (no shared substantive token)")

    # --- concrete when -------------------------------------------------------
    close_low = card.close.lower()
    if not (card.close and card.close.strip()):
        v.append("the close is empty")
    elif not (any(tok in close_low for tok in _WHEN_TOKENS) or _DATE_RE.search(card.close)):
        v.append("the close names no concrete when")

    # --- ~4 lines / ~10s -----------------------------------------------------
    lines = [ln for ln in card.text.splitlines() if ln.strip()]
    if len(lines) > MAX_CARD_LINES:
        v.append(f"the card is {len(lines)} lines (> {MAX_CARD_LINES}) — it must read in ~10s")
    if len(card.text) > MAX_CARD_CHARS:
        v.append(f"the card is {len(card.text)} chars (> {MAX_CARD_CHARS}) — too long to glance")

    # --- never a grade / hedge anywhere --------------------------------------
    # A leading-letter lookbehind so a tell isn't matched inside a larger word
    # (e.g. "grade" must not fire on "degrade" / "upgrade").
    blob = " ".join([card.why_it_matters, card.move, card.on_his_side, card.close]).lower()
    for tell in _FORBIDDEN_TONE:
        if re.search(r"(?<![a-z])" + re.escape(tell), blob):
            v.append(f"not-a-tutor tell in the card: {tell!r}")

    return v


def passes_tone_gate(card: MentorCard, *, decision: MentorDecision, note: NoteView) -> bool:
    """True iff the card has **no** human-tutor-gate violations."""
    return not tone_gate_violations(card, decision=decision, note=note)


def assert_tone_gate(card: MentorCard, *, decision: MentorDecision, note: NoteView) -> None:
    """Raise `ToneGateError` (with the violation list) iff the card fails the gate."""
    violations = tone_gate_violations(card, decision=decision, note=note)
    if violations:
        raise ToneGateError(violations)

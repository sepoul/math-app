"""Candidate signals + the `SignalExtractor` seam (issue #69).

Detection reads a trailing window of daily notes and emits a *set of candidate
signals* — the raw material #70's restraint policy then accepts or silences.
This module fixes the **contract** (`CandidateSignal`) and the one **LLM-shaped
seam** (`SignalExtractor`) the deterministic detection pass in `detection.py`
plumbs together.

Two design rules from the epic drive the shapes here:

  * **All book grounding rides through #68's resolver.** A `CandidateSignal`
    carries a `GroundedAnchor` (from `anchor.py`) — never a hand-rolled citation.
    Detection resolves every candidate's anchor via `resolve_anchor`; a candidate
    that will not resolve to at least ``section-grounded`` is dropped upstream, so
    a `CandidateSignal` that *exists* always names a real spot in the book.
  * **The genuinely LLM-shaped work is injectable, not inline.** Pulling a
    *verbatim* hedge quote out of a transcript, and judging a struggle's
    **resolution clause** (abandoned vs. resolved vs. still-in-progress), is
    model work. It lives behind the `SignalExtractor` Protocol — exactly like
    `BookRetrieveFn` is the seam onto retrieval — so the detection *policy*
    (which observations survive, how bridges canonicalize) stays deterministic
    and unit-testable with an in-memory fake extractor. This module makes **no**
    model call.

`detection.py` owns the plumbing; this module owns the vocabulary.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from mathai.math_book.models import RetrievalIntent
from mathai.math_mentor.anchor import GroundedAnchor

if TYPE_CHECKING:  # avoid a runtime import cycle (detection.py imports this module)
    from mathai.math_mentor.detection import NoteView

# --- the candidate taxonomy ---------------------------------------------------

#: The three candidate kinds. `abandoned_crux` / `unverified_proof` are *repair*
#: signals (something to shore up); `ripe_bridge` is a *connect* signal (two
#: distinct threads that are secretly the same object — time to link them).
CandidateKind = Literal["abandoned_crux", "unverified_proof", "ripe_bridge"]

#: A struggle's disposition, read from its **resolution clause** — NOT from
#: effort language. This is the distinction the epic insists on: "that was
#: brutal but I finally saw it" is ``resolved`` (a *win*, not a crux); "I'll just
#: assume it and move on" is ``abandoned``; "still chipping away, back tomorrow"
#: is ``in_progress`` (deliberate, not abandoned). Only ``abandoned`` survives
#: into a repair candidate.
Disposition = Literal["abandoned", "resolved", "in_progress"]


# --- the extractor's raw observations (its output, detection's input) ---------


class ExtractedStruggle(BaseModel):
    """One struggle/hedge the extractor pulled from a note's transcript.

    A pre-anchor, pre-policy observation. `verbatim_quote` MUST be a span copied
    *verbatim* from the transcript (empty string if the extractor found a
    struggle it could not quote — detection drops those). `disposition` is the
    extractor's reading of the **resolution clause**: the whole point of the seam
    is that judging "did he actually resolve this?" is model work, and the
    deterministic policy only keeps ``abandoned`` ones.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["abandoned_crux", "unverified_proof"] = Field(
        ..., description="Which repair signal this is (a proof he didn't verify vs. a crux he dropped)."
    )
    verbatim_quote: str = Field(
        ..., description="Verbatim transcript span evidencing the struggle ('' if none could be pulled)."
    )
    topic: str = Field(..., description="What the struggle is about — the topic used to resolve the anchor.")
    written_coordinate: Optional[str] = Field(
        None, description="A book coordinate the learner named (e.g. 'Problem 9.3'), if any."
    )
    disposition: Disposition = Field(
        ..., description="Resolution-clause reading: abandoned | resolved | in_progress."
    )


class ConceptMention(BaseModel):
    """One touch of a `concepts`-trail string, with the transcript moment it surfaced.

    The unit of *bridge* detection. Each mention names a concept the learner
    touched (a free-text `concepts` string like ``"SL(m)"``), the `topic` used to
    resolve it against the book, and the `verbatim_quote` where they touched it
    (bridges are candidates too, so they must carry a quote). Detection resolves
    each mention's anchor and clusters mentions whose anchors overlap in the book
    skeleton — two *distinct* concept strings landing in the same region form a
    bridge, even when the strings share no words.
    """

    model_config = ConfigDict(extra="forbid")

    concept: str = Field(..., description="The concepts-trail string this mention is about (e.g. 'kernel').")
    verbatim_quote: str = Field(
        ..., description="Verbatim transcript span where the concept surfaced ('' if none)."
    )
    topic: str = Field(..., description="Topic used to resolve this concept's anchor (may equal `concept`).")
    written_coordinate: Optional[str] = Field(
        None, description="A book coordinate the learner named for this concept, if any."
    )


# --- the emitted contract -----------------------------------------------------


class CandidateSignal(BaseModel):
    """A grounded candidate the detection pass emits — repair or connect.

    This is the #69 contract, consumed by #70 (arbitration) and #71. It is a
    *candidate*, not a decision: detection makes **no** fire/silence call. Its
    invariant — enforced by `detection.py` — is the epic's "nameable anchor"
    rule: `grounded_anchor.trust_level` is always ``grounded`` or
    ``section-grounded`` (never ``ungrounded``), and `verbatim_quote` is always a
    non-empty transcript span. A candidate that could not satisfy both is dropped
    before it ever becomes a `CandidateSignal`.
    """

    model_config = ConfigDict(extra="forbid")

    kind: CandidateKind = Field(..., description="abandoned_crux | unverified_proof | ripe_bridge.")
    verbatim_quote: str = Field(..., description="The verbatim transcript span this candidate rests on.")
    topic: str = Field(..., description="What the candidate is about (topic used for grounding).")
    written_coordinate: Optional[str] = Field(
        None, description="Book coordinate the learner named, if any (drives coordinate-first grounding)."
    )
    source_note_date: str = Field(..., description="Date (YYYY-MM-DD) of the note this candidate surfaced from.")
    grounded_anchor: GroundedAnchor = Field(
        ..., description="The #68-resolved anchor — always grounded or section-grounded (never ungrounded)."
    )


# --- kind → retrieval intent mapping ------------------------------------------
#
# An open seam (issue: "Intent mapping per signal kind → book_retrieve.intent").
# The mapping steers the hybrid mix / graph expansion #64 gates on:
#   * `unverified_proof` → "proof": he wrote a proof and didn't check it; the
#     proof intent surfaces the theorem's own proof/derivation to verify against.
#   * `abandoned_crux`   → "theorem": a crux is the central *result/step* he gave
#     up on; the theorem intent surfaces the key statement he stalled at.
#   * `ripe_bridge`      → "general": bridging two distinct concepts wants the
#     broad hybrid mix (no narrowing) so the overlap region is found on its own
#     terms — the issue suggests general/definition; we take "general".
# Defensible, not sacred — a downstream calibration pass can retune it.
_INTENT_BY_KIND: dict[CandidateKind, RetrievalIntent] = {
    "abandoned_crux": "theorem",
    "unverified_proof": "proof",
    "ripe_bridge": "general",
}


def intent_for_kind(kind: CandidateKind) -> RetrievalIntent:
    """Map a candidate kind to the `book_retrieve` intent used to resolve its anchor."""
    return _INTENT_BY_KIND[kind]


# --- the LLM-shaped seam ------------------------------------------------------


@runtime_checkable
class SignalExtractor(Protocol):
    """The single LLM-shaped seam of the detection pass.

    Two read-only extractions over a note, each of which is genuinely model work
    (reading natural language for hedges, quoting *verbatim*, judging a
    resolution clause, spotting which `concepts` a moment touched):

      * `extract_struggles(note)` → the hedges/uncertainties in the transcript,
        each with its verbatim quote and resolution disposition.
      * `extract_concept_mentions(note)` → the `concepts`-trail touches, each
        with the verbatim moment it surfaced, for bridge canonicalization.

    Production injects a Claude-backed implementation; tests inject an in-memory
    fake seeded with expected outputs (see `tests/corpus.py`). The detection
    *policy* around this seam is deterministic — it never calls a model itself.
    `runtime_checkable` so a fake can be `isinstance`-asserted against the port.
    """

    def extract_struggles(self, note: "NoteView") -> Sequence[ExtractedStruggle]:  # noqa: D401
        ...

    def extract_concept_mentions(self, note: "NoteView") -> Sequence[ConceptMention]:  # noqa: D401
        ...

"""The detection pass (issue #69) — trailing-window read-model + candidate signals.

This is **pure extraction logic**: read a trailing window of daily notes, emit
the *set* of grounded `CandidateSignal`s (repair + connect). It makes **no**
fire/silence decision — that is #70's restraint policy. It calls **no** model —
the one LLM-shaped step is injected as a `SignalExtractor`. It never touches the
book directly — every anchor is resolved through #68's `resolve_anchor`, whose
only data source is an injected `BookRetrieveFn`.

The pieces:

  * `NoteView` — a minimal typed view of one daily note in the window, holding
    *exactly* the fields detection reads. Mirrors the real `math_notes` types
    (`DailyNoteArtifact.transcript`, `NoteSynthesis.concepts` / `.markdown`,
    `NoteMagnitude.density_tier`, `NoteFlair.dont_spoil`); `from_daily_note`
    adapts the real artifact into it so the core logic never depends on a live
    platform.
  * `detect_candidates` — the pass. Repair candidates come from the extractor's
    struggles (verbatim quote required; **resolution clause**, not effort,
    decides survival; anchor must resolve). Bridge candidates come from
    clustering concept mentions whose **retrieval anchors overlap** in the book
    skeleton — distinct concept strings landing in the same region, not string
    matching.

The four invariants a surviving `CandidateSignal` guarantees:
  1. it carries a **non-empty verbatim transcript quote** (AC1);
  2. a repair candidate's disposition is **abandoned** — resolved/in-progress
     struggles are dropped (AC2, resolution clause not effort);
  3. a bridge is two **distinct** concepts whose anchors **overlap** by
     retrieval, spanning ≥2 notes (AC3);
  4. its `grounded_anchor` is **grounded or section-grounded**, never
     ungrounded (AC4, "nameable anchor").
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from mathai.math_mentor.anchor import GroundedAnchor, resolve_anchor
from mathai.math_mentor.port import BookRetrieveFn
from mathai.math_mentor.signals import (
    CandidateSignal,
    CandidateKind,
    ConceptMention,
    ExtractedStruggle,
    SignalExtractor,
    intent_for_kind,
)

if TYPE_CHECKING:  # math_notes is imported lazily inside from_daily_note (never at load)
    from mathai.math_notes.artifacts import DailyNoteArtifact
    from mathai.math_notes.models import NoteFlair

# --- tunables (open seams; provisional) ---------------------------------------

#: Default trailing-window size (notes). ``None`` here means "use every note the
#: caller passed"; a concrete int keeps only the most recent N by date. An open
#: seam settled with #56 — exposed as a parameter so calibration lives in one
#: place. Detection reads a *window*, so the size is a first-class knob.
DEFAULT_WINDOW: Optional[int] = None

#: How many leading `heading_path` levels two anchors must share to count as
#: landing in the same skeleton region for bridge canonicalization. 2 = same
#: chapter + section (e.g. ``["Chapter 2: Manifolds", "§9 …"]``). This is the
#: operationalization of the epic's "related/adjacent skeleton nodes": siblings /
#: cousins under one section are adjacent. Exact same node (equal ``node_id``)
#: also counts (see `anchors_overlap`).
BRIDGE_MIN_SHARED_DEPTH = 2

DensityTier = Literal["brief", "standard", "deep"]


# --- the read-model view ------------------------------------------------------


class NoteView(BaseModel):
    """A minimal typed view of one daily note in the trailing window.

    Holds **exactly** the fields the detection pass reads — no more — so the core
    logic is testable without a live platform. Each field mirrors a real
    `math_notes` field (see `from_daily_note`):

      * `transcript` — clean ASR; the **primary detection surface** (his verbal
        hedges live here, not in page OCR).
      * `concepts` — the free-text cross-track trail (bridge ripeness).
      * `density_tier` — the magnitude bucket. Context only: detection triggers
        on the transcript's **verbal cue**, not on density (a light day with a
        real hedge still fires).
      * `dont_spoil` — the learner flair. Carried for downstream policy (#70);
        detection extracts candidates regardless (pure extraction).
      * `markdown` — the synthesized note (source of the celebration / "catch").
    """

    model_config = ConfigDict(extra="forbid")

    date: str = Field(..., description="Study day, YYYY-MM-DD (e.g. '2025-06-24').")
    transcript: Optional[str] = Field(
        None, description="Clean ASR transcript — the primary detection surface."
    )
    concepts: list[str] = Field(
        default_factory=list, description="Free-text concepts trail (cross-track recurrence)."
    )
    density_tier: DensityTier = Field(
        "standard", description="Magnitude bucket (brief|standard|deep) — context, not a trigger."
    )
    dont_spoil: bool = Field(
        False, description="The dont_spoil flair — carried for #70's policy; detection is flair-blind."
    )
    markdown: Optional[str] = Field(
        None, description="Synthesized note markdown (source of the celebration/catch)."
    )


def from_daily_note(
    note: "DailyNoteArtifact", *, flairs: "Sequence[NoteFlair] | None" = None
) -> NoteView:
    """Adapt a real `math_notes.DailyNoteArtifact` (+ its flairs) into a `NoteView`.

    The thin platform → contract adapter (mirrors #68's `adapter.py`). Reads the
    artifact's `transcript`, its `synthesis.concepts` / `synthesis.markdown`, and
    its `magnitude.density_tier`; the `dont_spoil` flair is passed **alongside**
    because flairs live on the *job input* (`MathNotesInput.flairs`), not on the
    persisted artifact.

    `math_notes` is imported **lazily** (like the platform adapter's lazy
    `ai_platform` import) so importing this module — and running the core
    detection logic on hand-built `NoteView`s — never requires `math_notes`.
    """
    from mathai.math_notes.artifacts import DailyNoteArtifact  # noqa: F401  (type clarity)
    from mathai.math_notes.models import NoteFlair

    synthesis = getattr(note, "synthesis", None)
    concepts = list(getattr(synthesis, "concepts", []) or []) if synthesis is not None else []
    markdown = getattr(synthesis, "markdown", None) if synthesis is not None else None

    magnitude = getattr(note, "magnitude", None)
    density_tier: DensityTier = (
        getattr(magnitude, "density_tier", "standard") if magnitude is not None else "standard"
    )

    flair_set = set(flairs or [])
    dont_spoil = NoteFlair.dont_spoil in flair_set

    return NoteView(
        date=str(getattr(note, "note_date", "")),
        transcript=getattr(note, "transcript", None),
        concepts=concepts,
        density_tier=density_tier,
        dont_spoil=dont_spoil,
        markdown=markdown,
    )


# --- the trailing window ------------------------------------------------------


def trailing_window(notes: Sequence[NoteView], size: Optional[int]) -> list[NoteView]:
    """Sort notes by date ascending and keep the most recent `size` (all if None)."""
    ordered = sorted(notes, key=lambda n: n.date)
    if size is not None and size >= 0:
        ordered = ordered[-size:] if size else []
    return ordered


# --- skeleton-region overlap (bridge canonicalization primitive) --------------


def _common_prefix_len(a: Sequence[str], b: Sequence[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x == y:
            n += 1
        else:
            break
    return n


def anchors_overlap(a: GroundedAnchor, b: GroundedAnchor) -> bool:
    """Do two grounded anchors land on **related/adjacent** skeleton nodes?

    The epic's bridge test, resolved via retrieval — **not** string overlap of
    the concept names. Two anchors overlap iff either:

      * they resolved to the **exact same node** (equal, non-null ``node_id``), or
      * their `heading_path`s share a prefix of at least
        `BRIDGE_MIN_SHARED_DEPTH` levels (same chapter+section → adjacent nodes).

    ("Linked via the structure graph" — following `references`/`depends_on`
    edges — would need a skeleton-walk seam beyond the `GroundedAnchor` contract;
    shared-region is the operationalization we can reach through #68's resolver.)
    """
    if a.node_id is not None and a.node_id == b.node_id:
        return True
    if not a.heading_path or not b.heading_path:
        return False
    return _common_prefix_len(a.heading_path, b.heading_path) >= BRIDGE_MIN_SHARED_DEPTH


# --- the detection pass -------------------------------------------------------


def _resolve(
    retrieve: BookRetrieveFn,
    book_id: str,
    *,
    coordinate: Optional[str],
    topic: str,
    kind: CandidateKind,
) -> GroundedAnchor:
    """Resolve an anchor through #68's resolver with the kind's retrieval intent."""
    return resolve_anchor(
        retrieve,
        book_id=book_id,
        coordinate=coordinate,
        topic=topic,
        intent=intent_for_kind(kind),
    )


def _repair_candidates(
    notes: Sequence[NoteView],
    retrieve: BookRetrieveFn,
    extractor: SignalExtractor,
    *,
    book_id: str,
) -> list[CandidateSignal]:
    """Struggles → repair candidates (abandoned_crux / unverified_proof).

    A struggle survives only if: it carries a **non-empty verbatim quote** (AC1),
    its **disposition is `abandoned`** — a resolved or still-in-progress struggle
    is not a repair candidate (AC2, resolution clause not effort) — and its
    anchor resolves to at least ``section-grounded`` (AC4).
    """
    out: list[CandidateSignal] = []
    for note in notes:
        struggle: ExtractedStruggle
        for struggle in extractor.extract_struggles(note):
            if not struggle.verbatim_quote.strip():
                continue  # AC1: no quote → no candidate
            if struggle.disposition != "abandoned":
                continue  # AC2: resolved/in_progress read from the resolution clause → not a crux
            anchor = _resolve(
                retrieve,
                book_id,
                coordinate=struggle.written_coordinate,
                topic=struggle.topic,
                kind=struggle.kind,
            )
            if anchor.trust_level == "ungrounded":
                continue  # AC4: no nameable anchor → not a candidate
            out.append(
                CandidateSignal(
                    kind=struggle.kind,
                    verbatim_quote=struggle.verbatim_quote,
                    topic=struggle.topic,
                    written_coordinate=struggle.written_coordinate,
                    source_note_date=note.date,
                    grounded_anchor=anchor,
                )
            )
    return out


class _AnchoredMention(BaseModel):
    """A concept mention paired with its resolved anchor (internal, bridge stage)."""

    model_config = ConfigDict(extra="forbid")

    date: str
    mention: ConceptMention
    anchor: GroundedAnchor


def _bridge_candidates(
    notes: Sequence[NoteView],
    retrieve: BookRetrieveFn,
    extractor: SignalExtractor,
    *,
    book_id: str,
) -> list[CandidateSignal]:
    """Concept mentions → ripe_bridge candidates, canonicalized by retrieval overlap.

    1. Resolve every concept mention's anchor (a mention must carry a verbatim
       quote per AC1, and resolve to ≥ section-grounded per AC4 — else it is
       dropped before clustering).
    2. Cluster the surviving anchored mentions by `anchors_overlap` (shared
       skeleton region), via union-find.
    3. A cluster is a **bridge** iff it holds ≥2 **distinct** concept strings
       AND spans ≥2 distinct notes (cross-track recurrence) — the same concept
       repeated, or a single-note coincidence, is not a bridge (AC3). The
       determinant chain (~5 distinct strings — SL(m)/kernel/regular level set —
       that share no word) clusters here purely because their anchors overlap.
    4. Emit one candidate per bridge cluster, represented by its **most recent**
       mention (ripeness peaks at the latest recurrence).
    """
    anchored: list[_AnchoredMention] = []
    for note in notes:
        mention: ConceptMention
        for mention in extractor.extract_concept_mentions(note):
            if not mention.verbatim_quote.strip():
                continue  # AC1: no quote → no candidate
            anchor = _resolve(
                retrieve,
                book_id,
                coordinate=mention.written_coordinate,
                topic=mention.topic,
                kind="ripe_bridge",
            )
            if anchor.trust_level == "ungrounded":
                continue  # AC4: no nameable anchor → cannot bridge
            anchored.append(_AnchoredMention(date=note.date, mention=mention, anchor=anchor))

    # Union-find over pairwise anchor overlap.
    parent = list(range(len(anchored)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(anchored)):
        for j in range(i + 1, len(anchored)):
            if anchors_overlap(anchored[i].anchor, anchored[j].anchor):
                union(i, j)

    clusters: dict[int, list[_AnchoredMention]] = {}
    for idx, am in enumerate(anchored):
        clusters.setdefault(find(idx), []).append(am)

    out: list[CandidateSignal] = []
    for members in clusters.values():
        distinct_concepts = {m.mention.concept.strip().lower() for m in members}
        distinct_dates = {m.date for m in members}
        if len(distinct_concepts) < 2 or len(distinct_dates) < 2:
            continue  # AC3: a bridge needs ≥2 distinct concepts recurring across ≥2 notes
        # Represent the bridge by its most recent mention (ripeness = latest recurrence).
        rep = max(members, key=lambda m: m.date)
        out.append(
            CandidateSignal(
                kind="ripe_bridge",
                verbatim_quote=rep.mention.verbatim_quote,
                topic=rep.mention.topic,
                written_coordinate=rep.mention.written_coordinate,
                source_note_date=rep.date,
                grounded_anchor=rep.anchor,
            )
        )
    return out


def detect_candidates(
    notes: Sequence[NoteView],
    retrieve: BookRetrieveFn,
    extractor: SignalExtractor,
    *,
    book_id: str,
    window: Optional[int] = DEFAULT_WINDOW,
) -> list[CandidateSignal]:
    """Run the detection pass over a trailing window and return the candidate set.

    **Pure extraction**: returns the SET of grounded `CandidateSignal`s (repair +
    connect); makes **no** fire/silence decision (that is #70). Every returned
    candidate satisfies all four invariants (verbatim quote, abandoned
    disposition for repairs, distinct-concept overlap for bridges, non-ungrounded
    anchor). All book access flows through `resolve_anchor(retrieve, …)`; the one
    LLM-shaped step is `extractor`. Both are injected — this function calls no
    model and does no retrieval of its own.

    Output is deterministically ordered (by source date, then kind) so callers
    and tests see a stable set.
    """
    windowed = trailing_window(notes, window)
    candidates = _repair_candidates(windowed, retrieve, extractor, book_id=book_id)
    candidates += _bridge_candidates(windowed, retrieve, extractor, book_id=book_id)
    candidates.sort(key=lambda c: (c.source_note_date, c.kind, c.topic))
    return candidates

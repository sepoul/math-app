"""Math-notes artifacts — the dated note a learner captures.

`DailyNoteArtifact` is a *blob-backed* document artifact: the bytes (a voice
note, optionally notebook photos) live in the storage plane, uploaded via
`POST /media`. One note → one artifact. The artifact carries the audio
`storage_ref` (+ content_type / byte_size, inherited from `BaseArtifact`),
the `transcript` the ingest produced, the raw per-photo extraction as nested
`pages` children, and the note-level `synthesis` (the cleaned-up, coherent
math). `GET /artifacts/{id}` hydrates `storage_ref` into a `storage_url` the
UI renders directly (an `<audio src=…>`).

Two phases produce it: faithful **extraction** (audio transcript + per-photo
raw transcription, no interpretation) then one holistic **synthesis** pass
(Opus, over the whole note) that reconstructs the intended math — a semantic
neighbour of the fuzzy notes, not a blind mirror. The raw extraction is kept
in the `pages` children as evidence; the synthesis is the strong-semantic
view. See `docs/daily-notes-redesign.md`.

`NotePageArtifact` is the **legacy** per-photo artifact (its own row, linked
by `source_note_id`). It is no longer minted — the page data now lives inline
on `DailyNoteArtifact.pages` — but the class stays registered so old rows
still hydrate and the migration can read them.
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_platform.jobs.artifact import BaseArtifact


class NotePage(BaseModel):
    """Faithful extraction of one notebook photo — a nested child of the note.

    Raw-only by design: `raw_text` is a faithful transcription of what's on
    the page (no LaTeX, no concepts — those are reconstructed note-level in
    `NoteSynthesis`). Held on `MathNotesState` in-flight and stored inline on
    `DailyNoteArtifact.pages`; never an artifact of its own.
    """

    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(..., ge=0)
    image_ref: str = Field(..., description="storage_ref of the source photo.")
    raw_text: Optional[str] = Field(
        None, description="Faithful plain-text transcription of the page."
    )
    diagram_description: Optional[str] = Field(
        None, description="Description of any diagram/figure on the page."
    )


# --- note magnitude (multi-modal density signal) -----------------------------
#
# `density_tier` is a coarse bucket over a note's *content volume*, fused across
# the three capture modalities — what the learner said (transcript), what they
# wrote (notebook pages), and how long they spoke (audio duration). It exists so
# downstream synthesis (S2/S3) can scale depth/effort to how much a note holds.
#
# Two design facts drive the weighting (see issue #15 / epic #14):
#   * `page_count` is the single strongest proxy for study *scope* — a 5-hour
#     session fills many more notebook pages than a 1-hour one — so it carries
#     the heaviest weight. Transcript + page text fill in the rest.
#   * Audio *duration* barely varies across the 2–7 min band these notes live
#     in, so it is captured for the record but NOT scored.
#
# Magnitude is meant to be *relative to the learner's own baseline* (every note
# sits in a narrow band, so absolute thresholds are weak signal). This story
# (S1) ships the **cold-start** path — absolute buckets against the reference
# units below — and leaves a real seam for normalization: pass a
# `MagnitudeBaseline` (the learner's recent-note medians) and the same signals
# are scored *relative* to their norm instead. Reading recent `daily_note`
# artifacts to build that baseline is the documented follow-up; until then
# `density_tier` falls back to absolute buckets.

DensityTier = Literal["brief", "standard", "deep"]

# Cold-start (absolute) scoring. Each signal contributes "points"; page_count
# dominates by design. Tuned so a *typical* 1–2 page, ~4k-char note lands in
# "standard", a terse no-page memo in "brief", and a multi-page content-rich
# session in "deep". These are deliberately coarse heuristics — S3's content
# assessment is the authoritative density estimate; this is just a cheap prior.
_POINTS_PER_PAGE = 1.0
_TRANSCRIPT_CHARS_PER_POINT = 3500.0
_PAGE_CHARS_PER_POINT = 3500.0

# Cut points on the fused score (shared by the absolute and relative paths).
_STANDARD_MIN_SCORE = 2.0
_DEEP_MIN_SCORE = 5.0

# Relative (baseline) scoring weights — a note exactly at the learner's medians
# (every ratio == 1) scores 3.0, i.e. solidly "standard"; ~0.7× baseline tips to
# "brief", ~1.7× to "deep". page_count stays the heaviest weight.
_BASELINE_PAGE_WEIGHT = 1.6
_BASELINE_TRANSCRIPT_WEIGHT = 0.9
_BASELINE_PAGE_CHARS_WEIGHT = 0.5


class MagnitudeBaseline(BaseModel):
    """A learner's recent-note medians — the yardstick `density_tier` scores a
    new note against so magnitude is *relative* to their own norm, not absolute.

    Building this from a learner's recent `daily_note` artifacts is a follow-up
    (epic #14); `density_tier` accepts it today so that wiring stays purely
    additive — pass it and scoring switches to the relative path, omit it and
    scoring falls back to absolute cold-start buckets.
    """

    model_config = ConfigDict(extra="forbid")

    transcript_chars: float = Field(..., ge=0.0)
    page_count: float = Field(..., ge=0.0)
    page_chars: float = Field(..., ge=0.0)


def _safe_ratio(value: float, base: float) -> float:
    """`value / base`, but defined when the learner's baseline for a signal is
    zero: an at-or-below-baseline value reads as 1.0 (typical), an above-baseline
    one as 2.0 (clearly more). Keeps the relative path total-free of div-by-zero."""
    if base > 0:
        return value / base
    return 1.0 if value <= base else 2.0


def density_tier(
    transcript_chars: int,
    page_count: int,
    page_chars: int,
    *,
    baseline: Optional[MagnitudeBaseline] = None,
) -> DensityTier:
    """Bucket a note's fused content-volume signals into brief/standard/deep.

    page_count is weighted the heaviest (strongest study-scope proxy); duration
    is intentionally excluded (it barely varies in this band). With `baseline`,
    each signal is scored *relative* to the learner's median; without one,
    against the absolute cold-start reference units.
    """
    if baseline is not None:
        score = (
            _BASELINE_PAGE_WEIGHT * _safe_ratio(page_count, baseline.page_count)
            + _BASELINE_TRANSCRIPT_WEIGHT
            * _safe_ratio(transcript_chars, baseline.transcript_chars)
            + _BASELINE_PAGE_CHARS_WEIGHT * _safe_ratio(page_chars, baseline.page_chars)
        )
    else:
        score = (
            _POINTS_PER_PAGE * page_count
            + transcript_chars / _TRANSCRIPT_CHARS_PER_POINT
            + page_chars / _PAGE_CHARS_PER_POINT
        )
    if score >= _DEEP_MIN_SCORE:
        return "deep"
    if score >= _STANDARD_MIN_SCORE:
        return "standard"
    return "brief"


class NoteMagnitude(BaseModel):
    """Multi-modal density signal for a note — "how much" it contains.

    Fuses the three modalities into one struct: `transcript_chars` (what they
    said), `page_count` + `page_chars` (what they wrote, the strongest scope
    proxy), and `duration_seconds` (a minor, often-absent signal — the default
    transcription model doesn't surface it). `density_tier` is the coarse bucket
    downstream synthesis reads to scale its depth/effort. Threaded on
    `MathNotesState` and persisted on `DailyNoteArtifact` (additive).
    """

    model_config = ConfigDict(extra="forbid")

    transcript_chars: int = Field(
        0, ge=0, description="Character length of the voice-note transcript."
    )
    page_count: int = Field(
        0, ge=0, description="Number of notebook pages captured (strongest scope proxy)."
    )
    page_chars: int = Field(
        0, ge=0, description="Total chars of faithful per-page transcription."
    )
    density_tier: DensityTier = Field(
        "brief",
        description="Coarse content-volume bucket (page_count-weighted): brief|standard|deep.",
    )
    duration_seconds: Optional[float] = Field(
        None,
        ge=0.0,
        description="Audio duration if the transcription surfaced it (minor signal).",
    )

    @classmethod
    def from_signals(
        cls,
        *,
        transcript: Optional[str] = None,
        pages: Optional[List["NotePage"]] = None,
        image_ref_count: Optional[int] = None,
        duration_seconds: Optional[float] = None,
        baseline: Optional[MagnitudeBaseline] = None,
    ) -> "NoteMagnitude":
        """Fuse a note's raw material into a `NoteMagnitude`.

        `page_count` is the count of captured photos — `max` of the extracted
        `pages` and `image_ref_count`, so it still reflects study scope when
        page extraction was skipped (no vision helper) and `pages` is empty.
        `page_chars` sums the faithful per-page text. Pure — no engine deps —
        so the live node and a backfill migration share it.
        """
        page_list = list(pages or [])
        transcript_chars = len(transcript or "")
        page_count = max(len(page_list), image_ref_count or 0)
        page_chars = sum(len(p.raw_text or "") for p in page_list)
        return cls(
            transcript_chars=transcript_chars,
            page_count=page_count,
            page_chars=page_chars,
            density_tier=density_tier(
                transcript_chars, page_count, page_chars, baseline=baseline
            ),
            duration_seconds=duration_seconds,
        )


class NoteSection(BaseModel):
    """One topical section of a note's synthesis — a heading, its prose+math,
    and the concepts it touches.

    The structured counterpart to the flat `markdown` blob: a multi-topic study
    session can render as one `NoteSection` per topic (each its own
    KaTeX-validated Markdown + concepts) instead of collapsing into a single
    block. Additive — short, single-topic notes leave `sections` empty and keep
    using the flat `markdown` field. Populating these is the adaptive/segmented
    synthesis pass's job (epic #14, S4); this story (S5) just owns the shape.
    """

    model_config = ConfigDict(extra="forbid")

    heading: str = Field(
        "", description="Short topical heading for the section (e.g. a `##` title)."
    )
    markdown: str = Field(
        "", description="Prose + embedded KaTeX-validated LaTeX for this section."
    )
    concepts: List[str] = Field(
        default_factory=list, description="Mathematical concepts this section touches."
    )


# --- synthesis plan (S3 assess/triage contract) ------------------------------
#
# `SynthesisPlan` is the output of the cheap assess/triage pass (S3) that *reads*
# a note before it is synthesized and decides how to treat it: how many distinct
# topics/problems it covers, how deep to go, where the natural segment
# boundaries are, and any study scope the learner stated out loud. It is the
# **authoritative** density read — a short (2–7 min) note can summarize 1–5 h of
# study, so audio duration (and even the `NoteMagnitude` heuristic) can't tell
# you this; only reading the content can. It reuses `DensityTier` for
# `depth_tier` so the plan and the magnitude signal speak the same vocabulary.
#
# The plan is threaded on `MathNotesState` and logged; S4 (adaptive/segmented
# synthesis) will consume it to scale depth/structure. It is an **in-flight**
# planning struct — NOT persisted on `DailyNoteArtifact` (the enriched synthesis
# schema is S5's job). Best-effort: the assess step returns `None` on any
# failure and synthesis falls back to its current single-pass behavior.

TopicKind = Literal[
    "exercise",
    "concept",
    "proof",
    "definition",
    "example",
    "dead_end",
    "breakthrough",
    "review",
    "other",
]


class PlanTopic(BaseModel):
    """One distinct topic / problem the note covers, as the assessor saw it."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., description="Short human title for the topic.")
    kind: TopicKind = Field(
        "other",
        description="What kind of material this is (exercise, concept, proof, dead_end, breakthrough, …).",
    )
    span_hint: Optional[str] = Field(
        None,
        description="Where in the note this topic appears (e.g. 'transcript opening', 'pages 1-2').",
    )


class SynthesisPlan(BaseModel):
    """Triage of a note, produced by the cheap assess pass (S3) before synthesis.

    The authoritative content-density read that lets synthesis scale depth and
    structure to how much a note actually holds. `topics` enumerates the distinct
    threads; `depth_tier` (shared vocabulary with `NoteMagnitude.density_tier`)
    says how deep to go; `suggested_sections` + `segment_boundaries` shape a
    map-reduce write-up of a big note; `study_scope_hint` captures any study
    scope the learner stated out loud ("~4 hours on X"); `rationale` records the
    reasoning. Threaded on `MathNotesState` and logged; consumed by S4. Not an
    artifact — never persisted on `DailyNoteArtifact`.
    """

    model_config = ConfigDict(extra="forbid")

    topics: List[PlanTopic] = Field(
        default_factory=list, description="Distinct topics/problems the note covers."
    )
    depth_tier: DensityTier = Field(
        "standard",
        description="How deep synthesis should go (content-assessed): brief|standard|deep.",
    )
    suggested_sections: int = Field(
        1, ge=1, description="How many sections the synthesis should produce (>= 1)."
    )
    segment_boundaries: List[str] = Field(
        default_factory=list,
        description="Short cues marking natural topic transitions, for segmented (map-reduce) synthesis.",
    )
    study_scope_hint: Optional[str] = Field(
        None,
        description="Study scope the learner stated in the note (e.g. '~4 hours on X'); None if unstated.",
    )
    rationale: Optional[str] = Field(
        None, description="Why the assessor chose this depth/structure."
    )
    model_used: Optional[str] = Field(
        None, description="The cheap model that produced the plan."
    )


class NoteSynthesis(BaseModel):
    """The note-level synthesis — one coherent, always-correct view of the math.

    Produced by the synthesis pass over the transcript + all page extractions.
    `markdown` is prose with embedded KaTeX-validated LaTeX (document mode);
    `concepts` and `summary` are note-level. Never reproduces an error the
    learner made — it reconstructs the intended math silently.

    Enriched (epic #14, S5) so a substantial session is more than one flat blob:
    `sections` carries per-topic structure, `depth_tier` marks how deep the
    synthesis rendered, and `magnitude` embeds the fused density signal the
    depth was scaled to. All three are additive (optional / default-empty) — the
    flat `markdown` stays the canonical field for short notes and back-compat,
    and rows written before the enrichment hydrate unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    markdown: Optional[str] = Field(
        None, description="Prose + embedded KaTeX-validated LaTeX for the whole note."
    )
    concepts: List[str] = Field(
        default_factory=list, description="Mathematical concepts the note touches."
    )
    summary: Optional[str] = Field(
        None, description="A short prose summary of the note."
    )
    # --- enrichment (additive, epic #14 / S5) --------------------------------
    # Per-topic structure for substantial sessions. Empty for short notes, which
    # keep using the flat `markdown` above. Filled by the adaptive synthesis
    # pass (S4); the flat `markdown` remains the back-compat / short-note field.
    sections: List[NoteSection] = Field(
        default_factory=list,
        description="Per-topic sections for a multi-topic note (empty for short notes).",
    )
    # How deep this synthesis was rendered — the same brief|standard|deep
    # vocabulary as `NoteMagnitude.density_tier`, so the depth chosen lines up
    # with the measured density. `None` when not set (old rows, short notes).
    depth_tier: Optional[DensityTier] = Field(
        None,
        description="Depth the synthesis rendered at (brief|standard|deep); None if unset.",
    )
    # The fused density signal this synthesis was scaled to — embedded here so a
    # consumer of the synthesis has the magnitude inline (it is also persisted
    # top-level on `DailyNoteArtifact.magnitude`). Reuses S1's `NoteMagnitude`.
    magnitude: Optional[NoteMagnitude] = Field(
        None, description="Density signal the synthesis depth was scaled to (S1's NoteMagnitude)."
    )
    model_used: Optional[str] = Field(
        None, description="The model that produced the synthesis."
    )
    validation_attempts: int = Field(
        default=0, ge=0, description="How many validate_latex calls before converging."
    )


class DailyNoteArtifact(BaseArtifact):
    """One captured study note, tied to a calendar day — a self-contained document.

    `storage_ref` / `content_type` / `byte_size` are inherited from
    `BaseArtifact` and point at the uploaded **audio** blob. `transcript` is
    the voice-note transcription; `pages` holds the raw per-photo extraction
    (children); `synthesis` is the cleaned-up note-level math. `image_refs`
    holds the notebook-photo storage_refs.

    `pages`, `synthesis`, `magnitude`, and `schema_version` are additive
    (optional with defaults) so old rows — written before the redesign — still
    hydrate under the current class. `schema_version` is the migration's
    idempotency marker: old rows default to 1; the document redesign is 2; rows
    carrying `magnitude` (and the enriched, section-capable `synthesis` shape)
    are 3.
    """

    artifact_type: Literal["daily_note"] = "daily_note"
    note_date: date = Field(..., description="The study day this note belongs to.")
    created_by: Optional[str] = Field(None, description="The learner who captured it.")

    # Notebook photos captured alongside the voice note (storage_refs).
    image_refs: list[str] = Field(
        default_factory=list, description="Attached notebook-photo storage_refs."
    )

    # Produced by the ingest job's transcription node.
    transcript: Optional[str] = Field(None, description="Transcript of the voice note.")

    # Raw faithful extraction, one per photo (nested children).
    pages: list[NotePage] = Field(
        default_factory=list, description="Raw per-photo extraction (children)."
    )
    # The note-level cleaned-up math (the strong-semantic view).
    synthesis: Optional[NoteSynthesis] = Field(
        None, description="Note-level synthesised, always-correct math."
    )

    # Multi-modal density signal (additive, schema_version 3). Computed at the
    # end of extraction and threaded through state; `None` on rows written
    # before S1 (they hydrate fine — additive + the `schema_version` guard).
    magnitude: Optional[NoteMagnitude] = Field(
        None, description="Fused content-density signal (transcript + pages + duration)."
    )

    # Combined readable transcription of `image_refs` (legacy field, kept for
    # back-compat on old rows; superseded by `pages` + `synthesis`).
    ocr_text: Optional[str] = Field(
        None, description="Legacy combined text/LaTeX parsed from the note's photos."
    )

    # Additive idempotency marker. 1 = pre-redesign; 2 = document redesign
    # (pages + synthesis inline); 3 = carries `magnitude` AND the enriched,
    # section-capable `synthesis` shape (sections + depth_tier + embedded
    # magnitude). The S5 synthesis enrichment rides on 3 rather than minting a 4:
    # it only adds optional fields and ships no backfill that populates them, so
    # nothing needs re-versioning. The next bump (to 4) belongs to the migration
    # that actually *populates* sections — the adaptive re-synthesis pass (S4,
    # #18) — where a fresh idempotency marker is meaningful. Old rows default to
    # 1 and hydrate fine — every bump only added optional fields.
    schema_version: int = Field(
        default=1,
        ge=1,
        description="Document shape version (1=pre-redesign, 2=document, 3=magnitude + enriched synthesis).",
    )


class NotePageArtifact(BaseArtifact):
    """LEGACY per-photo artifact — no longer minted, kept for back-compat.

    Before the document redesign, each photo was minted as its own
    `note_page` row linked to the parent via `source_note_id`. New ingests
    embed page data on `DailyNoteArtifact.pages` instead, but this class stays
    registered so old rows still hydrate on read and the migration
    (`scripts/migrate_notes_to_document.py`) can query them as its source.
    """

    artifact_type: Literal["note_page"] = "note_page"
    note_date: date = Field(..., description="The study day this page belongs to.")
    created_by: Optional[str] = Field(None, description="The learner who captured it.")
    source_note_id: UUID = Field(..., description="Parent DailyNoteArtifact id.")
    image_ref: str = Field(..., description="storage_ref of the source photo.")
    page_index: int = Field(..., ge=0, description="Order among the note's photos.")
    text: Optional[str] = Field(None, description="Plain-text transcription of the page.")
    latex: Optional[str] = Field(None, description="Math on the page, transcribed as LaTeX.")
    diagram_description: Optional[str] = Field(
        None, description="Description of any diagram/figure on the page."
    )
    concepts: List[str] = Field(
        default_factory=list, description="Mathematical concepts the page touches."
    )


MATH_NOTES_ARTIFACTS: dict[str, type[BaseArtifact]] = {
    DailyNoteArtifact.model_fields["artifact_type"].default: DailyNoteArtifact,
    NotePageArtifact.model_fields["artifact_type"].default: NotePageArtifact,
}

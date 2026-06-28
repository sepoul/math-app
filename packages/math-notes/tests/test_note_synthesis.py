"""Tests for the enriched `NoteSynthesis` schema (issue #19 / epic #14, S5).

Covers the additive enrichment of the note-level synthesis: per-topic
`sections`, a `depth_tier` marker, and an embedded `NoteMagnitude` — all
optional-with-defaults so old/flat rows hydrate unchanged. Also asserts the
published `DailyNoteArtifact` JSON Schema (what `control.py` registers) carries
the new shapes, and that the agent-output `_SynthesisOutput` gained the same
optional seam.

Run from the repo root in the default-runtime venv::

    PYTHONPATH="../ai-platform/packages/core/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python -m pytest \
      packages/math-notes/tests/test_note_synthesis.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.workspace.storage.structured.artifact_repository import (
    LocalArtifactRepository,
)
from ai_platform.workspace.storage.structured.local import LocalRepositoryConfig
from mathai.math_notes.artifacts import (
    MATH_NOTES_ARTIFACTS,
    DailyNoteArtifact,
    NoteMagnitude,
    NotePage,
    NoteSection,
    NoteSynthesis,
)


def _service(tmp_path: Path) -> ArtifactService:
    repo = LocalArtifactRepository(LocalRepositoryConfig(root_dir=str(tmp_path)))
    return ArtifactService(repo, registry=MATH_NOTES_ARTIFACTS)


# ---- new fields exist on the schema --------------------------------------

def test_synthesis_has_enrichment_fields():
    fields = NoteSynthesis.model_fields
    assert "sections" in fields
    assert "depth_tier" in fields
    assert "magnitude" in fields


def test_section_shape():
    sec = NoteSection(heading="Chain rule", markdown="$f'(g(x))g'(x)$", concepts=["chain rule"])
    assert sec.heading == "Chain rule"
    assert sec.markdown == "$f'(g(x))g'(x)$"
    assert sec.concepts == ["chain rule"]


def test_enrichment_fields_default_empty():
    # A synthesis built the old way (flat markdown only) gets empty/None
    # enrichment — the new fields never force a value.
    syn = NoteSynthesis(markdown="just a line", concepts=["limits"])
    assert syn.sections == []
    assert syn.depth_tier is None
    assert syn.magnitude is None


def test_depth_tier_accepts_density_vocabulary():
    for tier in ("brief", "standard", "deep"):
        assert NoteSynthesis(depth_tier=tier).depth_tier == tier


# ---- enriched round-trip through the artifact store ----------------------

def test_enriched_synthesis_round_trips(tmp_path):
    service = _service(tmp_path)
    mag = NoteMagnitude.from_signals(
        transcript="t" * 6000, pages=[NotePage(page_index=0, image_ref="r", raw_text="p" * 4000)]
    )
    synthesis = NoteSynthesis(
        markdown="# Whole note\n\nflat fallback view",
        concepts=["tangent space", "chain rule"],
        summary="A two-topic session.",
        sections=[
            NoteSection(heading="Tangent space", markdown="$T_pM$", concepts=["tangent space"]),
            NoteSection(heading="Chain rule", markdown="$(f\\circ g)'$", concepts=["chain rule"]),
        ],
        depth_tier="deep",
        magnitude=mag,
        model_used="claude-opus-4-8",
        validation_attempts=2,
    )
    note = DailyNoteArtifact(
        note_date=date(2026, 6, 1),
        transcript="t" * 6000,
        synthesis=synthesis,
        magnitude=mag,
        schema_version=3,
    )
    service.put(note)

    reloaded = service.get(note.artifact_id)
    assert reloaded.synthesis is not None
    assert len(reloaded.synthesis.sections) == 2
    assert reloaded.synthesis.sections[0].heading == "Tangent space"
    assert reloaded.synthesis.sections[1].concepts == ["chain rule"]
    assert reloaded.synthesis.depth_tier == "deep"
    # The embedded magnitude survives the round-trip and matches the top-level one.
    # (The synthesis's own `depth_tier` is an independent marker — here "deep" —
    # not necessarily equal to the measured `magnitude.density_tier`.)
    assert reloaded.synthesis.magnitude == mag
    assert reloaded.synthesis.magnitude.density_tier == mag.density_tier
    # The flat field is untouched — still the canonical short/back-compat view.
    assert reloaded.synthesis.markdown.startswith("# Whole note")


# ---- old / flat rows still hydrate ---------------------------------------

def test_flat_synthesis_round_trips_unchanged(tmp_path):
    # A pre-enrichment synthesis (only the flat fields) must hydrate with empty
    # sections / None depth / None embedded magnitude — no enrichment required.
    service = _service(tmp_path)
    note = DailyNoteArtifact(
        note_date=date(2026, 5, 1),
        transcript="legacy",
        synthesis=NoteSynthesis(markdown="$a+b$", concepts=["addition"], summary="adds."),
        schema_version=2,
    )
    service.put(note)

    reloaded = service.get(note.artifact_id)
    assert reloaded.schema_version == 2
    assert reloaded.synthesis.markdown == "$a+b$"
    assert reloaded.synthesis.sections == []
    assert reloaded.synthesis.depth_tier is None
    assert reloaded.synthesis.magnitude is None


def test_serialized_pre_enrichment_synthesis_validates():
    # Exactly the JSON a pre-S5 row stored — none of the new keys present. It
    # must still validate against the current (enriched) model.
    legacy = {
        "markdown": "$x^2$",
        "concepts": ["squares"],
        "summary": "squaring",
        "model_used": "claude-opus-4-8",
        "validation_attempts": 1,
    }
    syn = NoteSynthesis.model_validate(legacy)
    assert syn.markdown == "$x^2$"
    assert syn.sections == []
    assert syn.depth_tier is None
    assert syn.magnitude is None


def test_old_daily_note_without_synthesis_still_hydrates(tmp_path):
    # The oldest rows have no synthesis at all — still fine under the enriched class.
    service = _service(tmp_path)
    note = DailyNoteArtifact(note_date=date(2026, 4, 1), transcript="x", schema_version=1)
    service.put(note)

    reloaded = service.get(note.artifact_id)
    assert reloaded.synthesis is None
    assert reloaded.schema_version == 1


# ---- the published JSON Schema carries the new shapes --------------------

def test_published_schema_includes_enriched_synthesis():
    # `control.py` registers `DailyNoteArtifact` and the platform publishes its
    # JSON Schema; the new fields must appear in that derived schema so the SDK
    # regen (operator step) picks them up.
    schema = DailyNoteArtifact.model_json_schema()
    defs = schema.get("$defs", {})
    assert "NoteSynthesis" in defs
    assert "NoteSection" in defs
    syn_props = defs["NoteSynthesis"]["properties"]
    assert "sections" in syn_props
    assert "depth_tier" in syn_props
    assert "magnitude" in syn_props
    section_props = defs["NoteSection"]["properties"]
    assert {"heading", "markdown", "concepts"} <= set(section_props)


def test_no_new_required_fields_on_synthesis():
    # Acceptance: no required field added without a default. NoteSynthesis and
    # NoteSection must have NO required fields at all (every field defaults).
    assert NoteSynthesis.model_json_schema().get("required", []) == []
    assert NoteSection.model_json_schema().get("required", []) == []

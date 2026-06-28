"""Tests for `NoteMagnitude` — the multi-modal density signal (issue #15).

Covers the pure fusion + tiering (`from_signals` / `density_tier`, absolute and
baseline-relative), the additive persistence on `DailyNoteArtifact` (new rows
carry it at schema_version 3; old rows hydrate with `magnitude=None`), and the
backfill migration over a real `LocalArtifactRepository`.

Run from the repo root in the default-runtime venv::

    PYTHONPATH="../ai-platform/packages/core/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python -m pytest \
      packages/math-notes/tests/test_note_magnitude.py
"""
from __future__ import annotations

import importlib.util
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
    MagnitudeBaseline,
    NoteMagnitude,
    NotePage,
    density_tier,
)

# The migration lives in scripts/ (not an importable package), so load it by path.
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_note_magnitude.py"
_spec = importlib.util.spec_from_file_location("migrate_note_magnitude", _SCRIPT)
assert _spec and _spec.loader
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)


def _page(i: int, text: str) -> NotePage:
    return NotePage(page_index=i, image_ref=f"media/{i}/p.jpg", raw_text=text)


# ---- field fusion --------------------------------------------------------

def test_from_signals_counts_each_modality():
    mag = NoteMagnitude.from_signals(
        transcript="hello world",  # 11 chars
        pages=[_page(0, "abc"), _page(1, "de")],  # 3 + 2 = 5 chars, 2 pages
        duration_seconds=123.4,
    )
    assert mag.transcript_chars == 11
    assert mag.page_count == 2
    assert mag.page_chars == 5
    assert mag.duration_seconds == 123.4


def test_page_count_falls_back_to_image_ref_count_when_extraction_skipped():
    # No `pages` extracted (no vision helper), but two photos were captured —
    # page_count must still reflect study scope.
    mag = NoteMagnitude.from_signals(transcript="x", pages=[], image_ref_count=2)
    assert mag.page_count == 2
    assert mag.page_chars == 0


def test_from_signals_handles_empty_note():
    mag = NoteMagnitude.from_signals()
    assert mag.transcript_chars == 0
    assert mag.page_count == 0
    assert mag.page_chars == 0
    assert mag.duration_seconds is None
    assert mag.density_tier == "brief"


def test_none_page_text_counts_as_zero_chars():
    mag = NoteMagnitude.from_signals(pages=[NotePage(page_index=0, image_ref="r", raw_text=None)])
    assert mag.page_count == 1
    assert mag.page_chars == 0


# ---- absolute tiering (cold-start) ---------------------------------------

def test_tier_brief_for_terse_no_page_note():
    assert density_tier(transcript_chars=2500, page_count=0, page_chars=0) == "brief"


def test_tier_standard_for_typical_note():
    # ~1 page, ~4k transcript chars → middle of the band.
    assert density_tier(transcript_chars=4000, page_count=1, page_chars=1500) == "standard"


def test_tier_deep_for_multi_page_content_rich_note():
    assert density_tier(transcript_chars=6000, page_count=4, page_chars=4000) == "deep"


def test_page_count_is_the_heaviest_single_signal():
    # Same transcript/page text, but more pages climbs the tier — page_count
    # is the dominant proxy for study scope.
    base = dict(transcript_chars=1000, page_chars=500)
    assert density_tier(page_count=0, **base) == "brief"
    assert density_tier(page_count=2, **base) == "standard"
    assert density_tier(page_count=5, **base) == "deep"


def test_duration_does_not_affect_tier():
    # Duration is captured but never scored — two notes differing only in
    # duration tier identically.
    a = NoteMagnitude.from_signals(transcript="x" * 4000, pages=[_page(0, "y" * 1500)], duration_seconds=120.0)
    b = NoteMagnitude.from_signals(transcript="x" * 4000, pages=[_page(0, "y" * 1500)], duration_seconds=420.0)
    assert a.density_tier == b.density_tier


# ---- relative tiering (baseline seam) ------------------------------------

def test_baseline_makes_tier_relative():
    base = MagnitudeBaseline(transcript_chars=4000, page_count=2, page_chars=1500)
    # A note at the learner's medians is "standard"...
    assert density_tier(4000, 2, 1500, baseline=base) == "standard"
    # ...well above it is "deep"...
    assert density_tier(9000, 6, 4000, baseline=base) == "deep"
    # ...well below it is "brief".
    assert density_tier(800, 0, 200, baseline=base) == "brief"


def test_baseline_with_zero_page_norm_does_not_divide_by_zero():
    # A learner who never uploads photos: any pages read as "more than usual".
    base = MagnitudeBaseline(transcript_chars=4000, page_count=0, page_chars=0)
    # No pages, at-baseline transcript → still standard, no crash.
    assert density_tier(4000, 0, 0, baseline=base) == "standard"
    # Suddenly several pages pushes it up.
    assert density_tier(4000, 5, 3000, baseline=base) == "deep"


# ---- additive persistence ------------------------------------------------

def _service(tmp_path: Path) -> ArtifactService:
    repo = LocalArtifactRepository(LocalRepositoryConfig(root_dir=str(tmp_path)))
    return ArtifactService(repo, registry=MATH_NOTES_ARTIFACTS)


def test_new_note_round_trips_magnitude(tmp_path):
    service = _service(tmp_path)
    mag = NoteMagnitude.from_signals(transcript="hello", pages=[_page(0, "abc")])
    note = DailyNoteArtifact(
        note_date=date(2026, 6, 1),
        transcript="hello",
        pages=[_page(0, "abc")],
        magnitude=mag,
        schema_version=3,
    )
    service.put(note)

    reloaded = service.get(note.artifact_id)
    assert reloaded.schema_version == 3
    assert reloaded.magnitude == mag
    assert reloaded.magnitude.density_tier == mag.density_tier


def test_old_row_without_magnitude_still_hydrates(tmp_path):
    # A pre-S1 (schema_version 2) row carries no magnitude — it must hydrate
    # fine under the current class (additive field).
    service = _service(tmp_path)
    note = DailyNoteArtifact(note_date=date(2026, 5, 1), transcript="legacy", schema_version=2)
    service.put(note)

    reloaded = service.get(note.artifact_id)
    assert reloaded.magnitude is None
    assert reloaded.schema_version == 2
    assert reloaded.transcript == "legacy"


# ---- backfill migration --------------------------------------------------

def test_migration_backfills_magnitude_and_bumps_version(tmp_path):
    service = _service(tmp_path)
    note = DailyNoteArtifact(
        note_date=date(2026, 1, 1),
        transcript="some transcript text",
        pages=[_page(0, "page one"), _page(1, "page two")],
        image_refs=["media/0/p.jpg", "media/1/p.jpg"],
        schema_version=2,
    )
    service.put(note)

    rec = migrate._migrate_one(service, note, apply=True)
    assert rec["status"] == "updated"

    reloaded = service.get(note.artifact_id)
    assert reloaded.schema_version == 3
    assert reloaded.magnitude is not None
    assert reloaded.magnitude.transcript_chars == len("some transcript text")
    assert reloaded.magnitude.page_count == 2
    assert reloaded.magnitude.page_chars == len("page one") + len("page two")
    # Neighbours untouched.
    assert reloaded.transcript == "some transcript text"
    assert len(reloaded.pages) == 2

    # Idempotent: a second pass finds nothing to do.
    rec2 = migrate._migrate_one(service, service.get(note.artifact_id), apply=True)
    assert rec2["status"] == "skipped"


def test_migration_dry_run_does_not_write(tmp_path):
    service = _service(tmp_path)
    note = DailyNoteArtifact(note_date=date(2026, 1, 2), transcript="x", schema_version=2)
    service.put(note)

    rec = migrate._migrate_one(service, note, apply=False)
    assert rec["status"] == "would-update"
    assert rec["density_tier"] == "brief"
    # Store still has no magnitude — dry run wrote nothing.
    reloaded = service.get(note.artifact_id)
    assert reloaded.magnitude is None
    assert reloaded.schema_version == 2

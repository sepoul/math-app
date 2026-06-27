"""Tests for the synthesis-delimiter migration.

Covers the pure delimiter conversion (inline/display, idempotency) and the
end-to-end script behaviour over a real `LocalArtifactRepository`: a note with
legacy `\\(...\\)` / `\\[...\\]` migrates to `$...$` / `$$...$$`, the migration
is idempotent, notes without `synthesis.markdown` are untouched, and no other
field is mutated.

Run from the repo root in the default-runtime venv::

    PYTHONPATH="../ai-platform/packages/core/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python -m pytest \
      packages/math-notes/tests/test_migrate_synthesis_delimiters.py
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
    NoteSynthesis,
)

# The migration lives in scripts/ (not an importable package), so load it by path.
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_synthesis_delimiters.py"
_spec = importlib.util.spec_from_file_location("migrate_synthesis_delimiters", _SCRIPT)
assert _spec and _spec.loader
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)


# ---- pure conversion ----

def test_convert_inline_and_display_delimiters():
    src = r"Let \(x\) be real. \[ x^2 \ge 0 \]"
    assert migrate.convert_delimiters(src) == "Let $x$ be real. $$ x^2 \\ge 0 $$"


def test_convert_is_idempotent():
    src = r"## H\nLet \(G\) be a group. \[ gH = Hg \]"
    once = migrate.convert_delimiters(src)
    assert migrate.convert_delimiters(once) == once
    assert "\\(" not in once and "\\[" not in once


def test_already_dollar_form_is_noop():
    src = "Inline $a+b$ and display\n$$\nc=d\n$$"
    assert migrate.convert_delimiters(src) == src


# ---- end-to-end over a LocalArtifactRepository ----

def _service(tmp_path: Path) -> ArtifactService:
    repo = LocalArtifactRepository(LocalRepositoryConfig(root_dir=str(tmp_path)))
    return ArtifactService(repo, registry=MATH_NOTES_ARTIFACTS)


def test_migration_converts_and_preserves_other_fields(tmp_path):
    service = _service(tmp_path)
    note = DailyNoteArtifact(
        note_date=date(2026, 1, 1),
        transcript="original transcript",
        synthesis=NoteSynthesis(
            markdown=r"## Cosets\nLet \(H \le G\). \[ gH = Hg \]",
            concepts=["cosets"],
            summary="about cosets",
        ),
    )
    service.put(note)

    rec = migrate._migrate_one(service, note, apply=True)
    assert rec["status"] == "updated"

    reloaded = service.get(note.artifact_id)
    assert reloaded.synthesis.markdown == "## Cosets\\nLet $H \\le G$. $$ gH = Hg $$"
    # Untouched neighbours.
    assert reloaded.transcript == "original transcript"
    assert reloaded.synthesis.concepts == ["cosets"]
    assert reloaded.synthesis.summary == "about cosets"

    # Idempotent: a second pass finds nothing to do.
    rec2 = migrate._migrate_one(service, service.get(note.artifact_id), apply=True)
    assert rec2["status"] == "skipped"


def test_migration_skips_note_without_markdown(tmp_path):
    service = _service(tmp_path)
    note = DailyNoteArtifact(note_date=date(2026, 1, 2), transcript="just a transcript")
    service.put(note)

    rec = migrate._migrate_one(service, note, apply=True)
    assert rec["status"] == "skipped"
    assert rec["reason"] == "no synthesis.markdown"

    reloaded = service.get(note.artifact_id)
    assert reloaded.synthesis is None
    assert reloaded.transcript == "just a transcript"


def test_dry_run_does_not_write(tmp_path):
    service = _service(tmp_path)
    note = DailyNoteArtifact(
        note_date=date(2026, 1, 3),
        synthesis=NoteSynthesis(markdown=r"\(a\)"),
    )
    service.put(note)

    rec = migrate._migrate_one(service, note, apply=False)
    assert rec["status"] == "would-update"
    # Store still holds the legacy form — dry run wrote nothing.
    assert service.get(note.artifact_id).synthesis.markdown == r"\(a\)"

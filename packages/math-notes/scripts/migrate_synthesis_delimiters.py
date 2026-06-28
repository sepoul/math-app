#!/usr/bin/env python
r"""Migrate `daily_note.synthesis.markdown` to canonical `$`-delimited math.

Existing notes store their synthesis with KaTeX-style LaTeX delimiters
(`\(...\)` inline, `\[...\]` display). The canonical Markdown-math format the
frontend now renders (real Markdown + KaTeX) uses dollar delimiters
(`$...$` inline, `$$...$$` display). This script rewrites the **content** of
both `synthesis.markdown` AND each `synthesis.sections[].markdown` (the
sectioned shape from epic #14) in place for every existing `daily_note`:

  \(  ->  $       \)  ->  $       \[  ->  $$      \]  ->  $$

It is the free, no-LLM repair for the issue #33 drift, where an interior
section's display math was emitted as `\[…\]` (renders raw) — the sections
coverage matters because the bad math usually lives in a `sections[]` entry
while the flat `markdown` is clean.

Nothing else is touched. The database schema is unchanged — `synthesis.markdown`
stays a `str`, so there is no version coupling: this runs against any deployed
backend. It mirrors `scripts/migrate_notes_to_document.py` (ArtifactService over
`make_backend()`, dry-run by default, JSON report, per-note isolation), but is
far lighter — pure string surgery, no model calls, so it needs **no Anthropic
key and no math-ui validator**.

It is **idempotent**: after the first pass no `\(`/`\)`/`\[`/`\]` remain, so a
re-run (or a note already in `$` form) is a no-op.

Run it in the **default-runtime** venv with the platform + package on
PYTHONPATH, pointed at the target backend. Example:

    BACKEND=supabase SUPABASE_URL=... SUPABASE_SECRET_KEY=... \
    SUPABASE_CONNECTION_STRING=... \
    PYTHONPATH="../ai-platform/packages/core/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python \
      packages/math-notes/scripts/migrate_synthesis_delimiters.py            # dry-run
    # ... review delimiter-migration-report.json, then:
      ... migrate_synthesis_delimiters.py --apply                            # write

`make_backend()` resolves `BACKEND`; the supabase backend reads `SUPABASE_URL`
/ `SUPABASE_SECRET_KEY` / `SUPABASE_CONNECTION_STRING` (all required) and
`SUPABASE_SCHEMA` (unset = `public`/prod).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.workspace.storage.backends import make_backend
from mathai.math_notes.artifacts import MATH_NOTES_ARTIFACTS, DailyNoteArtifact

# The delimiter conversion (`\(`→`$`, `\)`→`$`, `\[`→`$$`, `\]`→`$$`) lives in
# the domain (`mathai.math_notes.text`) so this repair migration and the live
# synthesis path share ONE proven, idempotent implementation. Re-exported here
# under the historical name so callers/tests keep referring to
# `migrate.convert_delimiters`.
from mathai.math_notes.text import convert_delimiters

__all__ = ["convert_delimiters", "main"]


def _build_service() -> ArtifactService:
    """ArtifactService over the env-selected backend, with the math_notes
    registry so `daily_note` rows hydrate."""
    backend = make_backend()
    return ArtifactService(backend.artifact_repo, registry=MATH_NOTES_ARTIFACTS)


def _has_content(value) -> bool:
    """True when `value` is a non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def _migrate_one(service: ArtifactService, note: DailyNoteArtifact, apply: bool) -> dict:
    """Migrate a single note. Returns a report record (never raises).

    Converts BOTH the flat `synthesis.markdown` AND each
    `synthesis.sections[].markdown` (the sectioned shape from epic #14) — an
    interior section can carry `\\[…\\]` even when the flat field is clean (that
    is exactly the issue #33 drift). A note is `updated` if ANY field changed.
    """
    rec: dict = {"artifact_id": str(note.artifact_id), "note_date": str(note.note_date)}
    try:
        synthesis = note.synthesis
        if synthesis is None:
            rec["status"] = "skipped"
            rec["reason"] = "no synthesis.markdown"
            return rec

        # Nothing with text to convert at all → same "skipped" terminal state as
        # before (keeps the migration a no-op on empty/transcript-only notes).
        section_markdowns = [s.markdown for s in synthesis.sections]
        if not _has_content(synthesis.markdown) and not any(
            _has_content(sm) for sm in section_markdowns
        ):
            rec["status"] = "skipped"
            rec["reason"] = "no synthesis.markdown"
            return rec

        # Compute conversions; a field "changes" only if its converted form
        # differs (idempotent — clean fields are untouched).
        changed_markdown = False
        new_markdown = synthesis.markdown
        if _has_content(synthesis.markdown):
            new_markdown = convert_delimiters(synthesis.markdown)
            changed_markdown = new_markdown != synthesis.markdown

        changed_sections: list[int] = []
        new_section_markdowns: list[str] = []
        for i, sm in enumerate(section_markdowns):
            converted = convert_delimiters(sm) if _has_content(sm) else sm
            new_section_markdowns.append(converted)
            if _has_content(sm) and converted != sm:
                changed_sections.append(i)

        if not changed_markdown and not changed_sections:
            # Already canonical (or no legacy delimiters present) → idempotent.
            rec["status"] = "skipped"
            rec["reason"] = "no legacy delimiters"
            return rec

        rec["changed"] = {
            "markdown": changed_markdown,
            "sections": changed_sections,
        }
        if apply:
            # Mutate only the markdown content (flat + per-section); every other
            # field is preserved, and `put` upserts by the same artifact_id
            # (created_at intact).
            if changed_markdown:
                synthesis.markdown = new_markdown
            for i in changed_sections:
                synthesis.sections[i].markdown = new_section_markdowns[i]
            service.put(note)
            rec["status"] = "updated"
        else:
            rec["status"] = "would-update"
        return rec
    except Exception as exc:  # noqa: BLE001 — isolate per-note failures
        rec["status"] = "failed"
        rec["reason"] = f"{type(exc).__name__}: {exc}"
        return rec


def _main(args: argparse.Namespace) -> int:
    service = _build_service()

    notes = [
        n for n in service.list_by_type("daily_note") if isinstance(n, DailyNoteArtifact)
    ]
    notes.sort(key=lambda n: n.note_date)
    if args.limit is not None:
        notes = notes[: args.limit]

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] scanned {len(notes)} daily_note artifact(s)")

    records: list[dict] = []
    for i, note in enumerate(notes, 1):
        rec = _migrate_one(service, note, args.apply)
        records.append(rec)
        tail = f"  {rec.get('reason', '')}" if rec["status"] == "failed" else ""
        print(f"  ({i}/{len(notes)}) {rec['artifact_id']} [{rec['note_date']}] -> "
              f"{rec['status']}{tail}")

    counts: dict[str, int] = {}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "scanned": len(notes),
        "counts": counts,
        "failures": [r for r in records if r["status"] == "failed"],
        "records": records,
    }
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{mode} complete: {counts}")
    print(f"report → {args.report}")
    if not args.apply:
        print("re-run with --apply to write the converted documents.")
    # Non-zero exit on any per-note failure so an operator/CI notices.
    return 1 if counts.get("failed") else 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--apply", action="store_true",
                   help="Write the converted documents (default: dry-run, no writes).")
    p.add_argument("--limit", type=int, default=None, help="Only process the first N notes.")
    p.add_argument("--report", default="delimiter-migration-report.json",
                   help="Where to write the JSON report.")
    return _main(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

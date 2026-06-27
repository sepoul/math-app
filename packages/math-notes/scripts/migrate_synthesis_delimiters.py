#!/usr/bin/env python
r"""Migrate `daily_note.synthesis.markdown` to canonical `$`-delimited math.

Existing notes store their synthesis with KaTeX-style LaTeX delimiters
(`\(...\)` inline, `\[...\]` display). The canonical Markdown-math format the
frontend now renders (real Markdown + KaTeX) uses dollar delimiters
(`$...$` inline, `$$...$$` display). This script rewrites the **content** of
`synthesis.markdown` in place for every existing `daily_note`:

  \(  ->  $       \)  ->  $       \[  ->  $$      \]  ->  $$

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

# The four legacy delimiters → their dollar equivalents. Each is replaced
# independently; the search strings are disjoint so replacement order is
# irrelevant, and the spec is literal: `\(`→`$`, `\)`→`$`, `\[`→`$$`, `\]`→`$$`.
_DELIMITERS: tuple[tuple[str, str], ...] = (
    (r"\(", "$"),
    (r"\)", "$"),
    (r"\[", "$$"),
    (r"\]", "$$"),
)


def convert_delimiters(markdown: str) -> str:
    r"""Rewrite legacy LaTeX delimiters to canonical `$`/`$$` math.

    Pure and idempotent: the output contains no `\(`/`\)`/`\[`/`\]`, so
    re-applying it is a no-op (and content already in `$` form is unchanged).
    """
    out = markdown
    for old, new in _DELIMITERS:
        out = out.replace(old, new)
    return out


def _build_service() -> ArtifactService:
    """ArtifactService over the env-selected backend, with the math_notes
    registry so `daily_note` rows hydrate."""
    backend = make_backend()
    return ArtifactService(backend.artifact_repo, registry=MATH_NOTES_ARTIFACTS)


def _migrate_one(service: ArtifactService, note: DailyNoteArtifact, apply: bool) -> dict:
    """Migrate a single note. Returns a report record (never raises)."""
    rec: dict = {"artifact_id": str(note.artifact_id), "note_date": str(note.note_date)}
    try:
        markdown = note.synthesis.markdown if note.synthesis else None
        if not isinstance(markdown, str) or not markdown.strip():
            rec["status"] = "skipped"
            rec["reason"] = "no synthesis.markdown"
            return rec

        converted = convert_delimiters(markdown)
        if converted == markdown:
            # Already canonical (or no legacy delimiters present) → idempotent.
            rec["status"] = "skipped"
            rec["reason"] = "no legacy delimiters"
            return rec

        if apply:
            # Mutate only the markdown content; every other field is preserved,
            # and `put` upserts by the same artifact_id (created_at intact).
            note.synthesis.markdown = converted
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

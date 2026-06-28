#!/usr/bin/env python
"""Backfill `daily_note.magnitude` for notes written before S1 (issue #15).

New ingests compute a `NoteMagnitude` at the end of extraction and persist it on
`DailyNoteArtifact` (schema_version 3). Rows written earlier hydrate fine
(`magnitude` is additive + None) but carry no density signal. This script
recomputes the signal **from data already on the row** — the stored
`transcript` + `pages` (and `byte_size`/duration are not re-derived here; the
historical duration isn't recoverable, so it stays None) — and stamps it,
bumping `schema_version` to 3.

It mirrors `scripts/migrate_synthesis_delimiters.py` /
`scripts/migrate_notes_to_document.py`: `ArtifactService` over `make_backend()`,
**dry-run by default**, a JSON report, per-note isolation, and full idempotency.
It is pure (`NoteMagnitude.from_signals` does no model calls), so it needs **no
Anthropic key and no math-ui validator**.

**Idempotent**: a note already at `schema_version >= 3` with a `magnitude` is
skipped, so a re-run is a no-op. (A v3 row that somehow lost its magnitude is
recomputed.)

Run it in the **default-runtime** venv with the platform + package on
PYTHONPATH, pointed at the target backend. Example::

    BACKEND=supabase SUPABASE_URL=... SUPABASE_SECRET_KEY=... \
    SUPABASE_CONNECTION_STRING=... \
    PYTHONPATH="../ai-platform/packages/core/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python \
      packages/math-notes/scripts/migrate_note_magnitude.py            # dry-run
    # ... review magnitude-backfill-report.json, then:
      ... migrate_note_magnitude.py --apply                            # write

`make_backend()` resolves `BACKEND`; the supabase backend reads `SUPABASE_URL`
/ `SUPABASE_SECRET_KEY` / `SUPABASE_CONNECTION_STRING` (all required) and
`SUPABASE_SCHEMA` (unset = `public`/prod).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.workspace.storage.backends import make_backend
from mathai.math_notes.artifacts import (
    MATH_NOTES_ARTIFACTS,
    DailyNoteArtifact,
    NoteMagnitude,
)

# Rows at/after this version already carry a magnitude (new ingests stamp it).
_MAGNITUDE_SCHEMA_VERSION = 3


def _build_service() -> ArtifactService:
    """ArtifactService over the env-selected backend, with the math_notes
    registry so `daily_note` rows hydrate."""
    backend = make_backend()
    return ArtifactService(backend.artifact_repo, registry=MATH_NOTES_ARTIFACTS)


def _migrate_one(service: ArtifactService, note: DailyNoteArtifact, apply: bool) -> dict:
    """Backfill a single note's magnitude. Returns a report record (never raises)."""
    rec: dict = {"artifact_id": str(note.artifact_id), "note_date": str(note.note_date)}
    try:
        if note.schema_version >= _MAGNITUDE_SCHEMA_VERSION and note.magnitude is not None:
            rec["status"] = "skipped"
            rec["reason"] = "already has magnitude"
            return rec

        magnitude = NoteMagnitude.from_signals(
            transcript=note.transcript,
            pages=note.pages,
            image_ref_count=len(note.image_refs),
            # Historical audio duration isn't recoverable from the stored row.
            duration_seconds=None,
        )
        rec["density_tier"] = magnitude.density_tier

        if apply:
            note.magnitude = magnitude
            note.schema_version = max(note.schema_version, _MAGNITUDE_SCHEMA_VERSION)
            service.put(note)  # upsert by artifact_id → in-place overwrite
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
        tier = f" [{rec['density_tier']}]" if rec.get("density_tier") else ""
        print(f"  ({i}/{len(notes)}) {rec['artifact_id']} [{rec['note_date']}] -> "
              f"{rec['status']}{tier}{tail}")

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
        print("re-run with --apply to write the backfilled documents.")
    # Non-zero exit on any per-note failure so an operator/CI notices.
    return 1 if counts.get("failed") else 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--apply", action="store_true",
                   help="Write the backfilled documents (default: dry-run, no writes).")
    p.add_argument("--limit", type=int, default=None, help="Only process the first N notes.")
    p.add_argument("--report", default="magnitude-backfill-report.json",
                   help="Where to write the JSON report.")
    return _main(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Re-synthesize existing `daily_note` artifacts through the adaptive pass (S4).

The adaptive/segmented synthesis pass (epic #14, S4 / #18) is the first to
*populate* `NoteSynthesis.sections` — multi-topic notes are written up
topic-by-topic (map-reduce) instead of one flat blob. New ingests carry that
shape at `schema_version = 4` (`SECTIONED_SCHEMA_VERSION`). Rows written before
S4 hydrate fine (the section fields are additive) but their `synthesis` is the
older single-pass flat view with no sections. This script re-synthesizes those
rows **in place, non-destructively**:

  for each daily_note with schema_version < 4:
    - read its already-extracted material (transcript + inline pages)
    - run the cheap assess pass (S3) over it → a SynthesisPlan
    - run the SAME adaptive synthesis the live ingest uses, plan-driven:
        dense multi-topic → map-reduce sections; light note → single pass
    - rewrite the SAME artifact_id with the new synthesis + schema_version=4
    - reuse the row's stored `magnitude` (recomputed if absent)

It mirrors `scripts/migrate_notes_to_document.py`: `ArtifactService` over
`make_backend()`, **dry-run by default**, a JSON report, per-note isolation
(one failure never aborts the batch), and full idempotency (a row already at
`schema_version >= 4` is skipped, so a re-run only retries the not-yet-migrated
/ previously-failed). It re-runs the model, so like that script it needs the
**default-runtime** venv, `ANTHROPIC_API_KEY` (Opus synthesis + Haiku assess),
and the math-ui validator reachable (`UI_TOOL_API_URL`) for the `validate_latex`
loop on every segment.

A `None` synthesis is handled the same way as `migrate_notes_to_document`: when
the row HAS source material, `None` means the synthesis pass was *unavailable*
(no key / validator down / model error) — the row is left unmigrated for retry,
NOT sealed at v4. When the row has NO source, `None` is the correct terminal
state and the row is stamped v4 so a re-run doesn't reprocess it forever.

Run it pointed at the target backend. Example::

    BACKEND=supabase SUPABASE_URL=... SUPABASE_SECRET_KEY=... \
    SUPABASE_CONNECTION_STRING=... ANTHROPIC_API_KEY=... \
    UI_TOOL_API_URL=http://localhost:3000 \
    PYTHONPATH="../ai-platform/packages/core/src:../ai-platform/packages/worker/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python \
      packages/math-notes/scripts/migrate_synthesis_sections.py            # dry-run
    # ... review synthesis-sections-report.json, then:
      ... migrate_synthesis_sections.py --apply                            # write

`make_backend()` resolves `BACKEND`; the supabase backend reads `SUPABASE_URL`
/ `SUPABASE_SECRET_KEY` / `SUPABASE_CONNECTION_STRING` (all required) and
`SUPABASE_SCHEMA` (unset = `public`/prod).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.workspace.storage.backends import make_backend
from mathai.math_notes.artifacts import (
    MATH_NOTES_ARTIFACTS,
    SECTIONED_SCHEMA_VERSION,
    DailyNoteArtifact,
    NoteMagnitude,
)
from mathai.math_notes.workflow import assess_note, synthesize_note

# The synthesis prompt that ships with the package — the migration uses the
# exact instructions in the repo so its output matches the live pipeline.
_SYNTHESIS_PROMPT_PATH = Path(__file__).resolve().parent.parent / "instructions" / "synthesis.md"


def _load_synthesis_instructions() -> Optional[str]:
    try:
        return _SYNTHESIS_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return None


def _build_service() -> ArtifactService:
    """ArtifactService over the env-selected backend, with the math_notes
    registry so `daily_note` rows hydrate."""
    backend = make_backend()
    return ArtifactService(backend.artifact_repo, registry=MATH_NOTES_ARTIFACTS)


def _magnitude_for(note: DailyNoteArtifact) -> NoteMagnitude:
    """The row's stored magnitude, recomputed from data on the row if absent.

    Pre-S1 rows have no `magnitude`; `from_signals` is pure (no model calls), so
    we can rebuild it from the stored transcript + pages to feed the NOTE CONTEXT
    line. Historical audio duration isn't recoverable, so it stays None."""
    if note.magnitude is not None:
        return note.magnitude
    return NoteMagnitude.from_signals(
        transcript=note.transcript,
        pages=note.pages,
        image_ref_count=len(note.image_refs),
        duration_seconds=None,
    )


async def _migrate_one(
    service: ArtifactService,
    note: DailyNoteArtifact,
    instructions: Optional[str],
    apply: bool,
) -> dict:
    """Re-synthesize a single note. Returns a report record (never raises)."""
    rec: dict = {"artifact_id": str(note.artifact_id), "note_date": str(note.note_date)}
    try:
        if note.schema_version >= SECTIONED_SCHEMA_VERSION:
            rec["status"] = "skipped"
            rec["reason"] = f"already schema_version >= {SECTIONED_SCHEMA_VERSION}"
            return rec

        magnitude = _magnitude_for(note)
        # S3 assess → plan (best-effort; None just means single-pass synthesis).
        plan = await assess_note(note.transcript, note.pages)
        synthesis = await synthesize_note(
            note.transcript,
            note.pages,
            instructions,
            magnitude=magnitude,
            plan=plan,
        )

        rec["density_tier"] = magnitude.density_tier
        rec["plan_topics"] = len(plan.topics) if plan is not None else 0
        rec["synthesized"] = synthesis is not None
        if synthesis is not None:
            rec["sections"] = len(synthesis.sections)
            rec["concepts"] = len(synthesis.concepts)
            rec["markdown_chars"] = len(synthesis.markdown or "")

        # A `None` synthesis has two very different causes (see module docstring).
        # (a) The note has no source material → `None` is terminal; stamp it v4.
        # (b) The synthesis pass was *unavailable* → leave unmigrated for retry,
        # NOT sealed at v4, or the idempotent re-run skips it forever.
        has_source = bool((note.transcript or "").strip()) or any(
            (p.raw_text or "").strip() for p in note.pages
        )
        if synthesis is None and has_source:
            rec["status"] = "failed"
            rec["reason"] = (
                "synthesis unavailable (Anthropic key / validator / model); "
                "left unmigrated for retry"
            )
            return rec

        if apply:
            if synthesis is not None:
                note.synthesis = synthesis
            note.schema_version = SECTIONED_SCHEMA_VERSION
            service.put(note)  # upsert by artifact_id → in-place overwrite
            rec["status"] = "migrated"
        else:
            rec["status"] = "would-migrate"
        return rec
    except Exception as exc:  # noqa: BLE001 — isolate per-note failures
        rec["status"] = "failed"
        rec["reason"] = f"{type(exc).__name__}: {exc}"
        return rec


async def _main_async(args: argparse.Namespace) -> int:
    service = _build_service()
    instructions = _load_synthesis_instructions()
    if instructions is None:
        print(f"warning: could not read {_SYNTHESIS_PROMPT_PATH}; synthesizing without instructions",
              file=sys.stderr)

    notes = [n for n in service.list_by_type("daily_note") if isinstance(n, DailyNoteArtifact)]
    notes.sort(key=lambda n: n.note_date)
    if args.limit is not None:
        notes = notes[: args.limit]

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] {len(notes)} daily_note artifact(s) to consider "
          f"(math-ui validator: {args.ui_hint})")

    records: list[dict] = []
    for i, note in enumerate(notes, 1):
        rec = await _migrate_one(service, note, instructions, args.apply)
        records.append(rec)
        tail = f"  {rec.get('reason', '')}" if rec["status"] == "failed" else ""
        secs = f" [{rec['sections']} section(s)]" if rec.get("sections") is not None else ""
        print(f"  ({i}/{len(notes)}) {rec['artifact_id']} [{rec['note_date']}] -> "
              f"{rec['status']}{secs}{tail}")

    counts: dict[str, int] = {}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "counts": counts,
        "failures": [r for r in records if r["status"] == "failed"],
        "records": records,
    }
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{mode} complete: {counts}")
    print(f"report → {args.report}")
    if not args.apply:
        print("re-run with --apply to write the re-synthesized documents.")
    # Non-zero exit on any per-note failure so an operator/CI notices.
    return 1 if counts.get("failed") else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="Write the re-synthesized documents (default: dry-run, no writes).")
    p.add_argument("--limit", type=int, default=None, help="Only process the first N notes.")
    p.add_argument("--report", default="synthesis-sections-report.json",
                   help="Where to write the JSON report.")
    args = p.parse_args()
    args.ui_hint = os.getenv("UI_TOOL_API_URL", "http://localhost:3000 (default)")
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

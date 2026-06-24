#!/usr/bin/env python
"""Recycle existing `daily_note` artifacts into the one-document shape.

The daily-notes redesign (see `docs/daily-notes-redesign.md`) moved from
`DailyNoteArtifact` (parent) + N separate `NotePageArtifact` rows to ONE
`DailyNoteArtifact` document that embeds the pages and carries a note-level
`synthesis`. This script migrates existing production notes **in place,
non-destructively**:

  for each daily_note with schema_version < 2:
    - read its already-extracted material (transcript + sibling note_page text)
    - build NotePage children from that text (no re-transcribe / re-vision)
    - run the SAME synthesis pass the live ingest uses (one Opus call/note)
    - rewrite the SAME artifact_id with pages + synthesis + schema_version=2
    - leave the old note_page rows untouched

It is **idempotent** (notes already at schema_version >= 2 are skipped, so a
re-run only retries the not-yet-migrated / previously-failed), **resumable**
(per-note isolation; one failure never aborts the batch), and **tracked** (a
`migration-report.json` records per-note status). Dry-run by default.

Run it in the **default-runtime** venv (synthesis needs `basic_agent` /
Anthropic) with the platform + package on PYTHONPATH, pointed at the target
backend, with the math-ui validator reachable (`UI_TOOL_API_URL`). Example:

    BACKEND=supabase SUPABASE_URL=... SUPABASE_SECRET_KEY=... \
    SUPABASE_CONNECTION_STRING=... ANTHROPIC_API_KEY=... \
    UI_TOOL_API_URL=http://localhost:3000 \
    PYTHONPATH="../ai-platform/packages/core/src:../ai-platform/packages/worker/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python \
      packages/math-notes/scripts/migrate_notes_to_document.py            # dry-run
    # ... review migration-report.json, then:
      ... migrate_notes_to_document.py --apply                            # write

`make_backend()` resolves `BACKEND`; the supabase backend reads
`SUPABASE_URL` / `SUPABASE_SECRET_KEY` / `SUPABASE_CONNECTION_STRING`
(all required) and `SUPABASE_SCHEMA` (unset = `public`/prod). Synthesis
needs `ANTHROPIC_API_KEY` (the Opus pass) and `UI_TOOL_API_URL` reachable
(the `validate_latex` loop).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_platform.jobs.artifact_service import ArtifactService
from ai_platform.workspace.storage.backends import make_backend
from mathai.math_notes.artifacts import (
    MATH_NOTES_ARTIFACTS,
    DailyNoteArtifact,
    NotePage,
    NotePageArtifact,
)
from mathai.math_notes.workflow import synthesize_note

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
    registry so `daily_note` / `note_page` rows hydrate and `note_page` is a
    valid filter field."""
    backend = make_backend()
    return ArtifactService(backend.artifact_repo, registry=MATH_NOTES_ARTIFACTS)


def _pages_for(service: ArtifactService, note: DailyNoteArtifact) -> list[NotePage]:
    """Recover the note's raw per-photo text from its legacy note_page rows."""
    siblings = service.query(
        artifact_type="note_page",
        fields={"source_note_id": str(note.artifact_id)},
    )
    pages: list[NotePageArtifact] = [
        s for s in siblings if isinstance(s, NotePageArtifact)
    ]
    pages.sort(key=lambda p: p.page_index)
    return [
        NotePage(
            page_index=p.page_index,
            image_ref=p.image_ref,
            # Old `text` was a faithful transcription — exactly the raw
            # substrate the synthesis pass consumes.
            raw_text=p.text,
            diagram_description=p.diagram_description,
        )
        for p in pages
    ]


async def _migrate_one(
    service: ArtifactService,
    note: DailyNoteArtifact,
    instructions: Optional[str],
    apply: bool,
) -> dict:
    """Migrate a single note. Returns a report record (never raises)."""
    rec: dict = {"artifact_id": str(note.artifact_id), "note_date": str(note.note_date)}
    try:
        if note.schema_version >= 2:
            rec["status"] = "skipped"
            rec["reason"] = "already schema_version >= 2"
            return rec

        pages = _pages_for(service, note)
        synthesis = await synthesize_note(note.transcript, pages, instructions)

        rec["pages"] = len(pages)
        rec["synthesized"] = synthesis is not None
        if synthesis is not None:
            rec["concepts"] = len(synthesis.concepts)
            rec["markdown_chars"] = len(synthesis.markdown or "")

        # A `None` synthesis has two very different causes. (a) The note has no
        # source material (no transcript, no page text) — `None` is the correct
        # terminal state, so migrate it. (b) The synthesis pass was *unavailable*
        # (no Anthropic key, validator unreachable, model error) —
        # `synthesize_note` swallows those and also returns `None`. We must NOT
        # seal (b) at schema_version=2: that would mark it migrated and the
        # idempotent re-run would skip it forever. Leave it as a failure so a
        # re-run (with the env fixed) retries it.
        has_source = bool((note.transcript or "").strip()) or any(
            (p.raw_text or "").strip() for p in pages
        )
        if synthesis is None and has_source:
            rec["status"] = "failed"
            rec["reason"] = (
                "synthesis unavailable (Anthropic key / validator / model); "
                "left unmigrated for retry"
            )
            return rec

        if apply:
            note.pages = pages
            note.synthesis = synthesis
            note.schema_version = 2
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
        print(f"  ({i}/{len(notes)}) {rec['artifact_id']} [{rec['note_date']}] -> "
              f"{rec['status']}" + (f"  {rec.get('reason','')}" if rec["status"] in ("failed",) else ""))

    counts: dict[str, int] = {}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "counts": counts,
        "records": records,
    }
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{mode} complete: {counts}")
    print(f"report → {args.report}")
    if not args.apply:
        print("re-run with --apply to write the migrated documents.")
    return 1 if counts.get("failed") else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="Write the migrated documents (default: dry-run, no writes).")
    p.add_argument("--limit", type=int, default=None, help="Only process the first N notes.")
    p.add_argument("--report", default="migration-report.json", help="Where to write the JSON report.")
    args = p.parse_args()
    import os
    args.ui_hint = os.getenv("UI_TOOL_API_URL", "http://localhost:3000 (default)")
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

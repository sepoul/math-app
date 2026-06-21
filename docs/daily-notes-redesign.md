# Daily Notes — extract→synthesize redesign + non-destructive data migration

> Agreed design as of 2026-06-21, to be implemented. Companion to memory
> `daily-notes-redesign`. The prompt-extraction groundwork (domain-owned
> instructions) already landed on branch `feat/daily-notes-improvements`.

## Context

Today the `math_notes` ingest interprets **per photo in isolation**: each image
runs a vision JSON parse (text/latex/concepts) followed by a per-photo
`validate_latex` agent loop. In production this yields **low-quality LaTeX** —
student notes are fuzzy by nature (they're studying, not publishing), and a
per-image pass faithfully mirrors the fuzz with no context to recover intent.

The redesign splits **extraction** (faithful, cheap, per-source) from
**synthesis** (one holistic Opus pass over the whole note). The win is
**cross-modal grounding**: the voice note disambiguates smudged handwriting and
vice-versa, so we reconstruct the math the student *meant* rather than copy what
they scrawled. As a bonus it cuts cost (gotcha #3: N×(vision+validate) → N cheap
extractions + 1 synthesis) and the read-path N+1 (gotcha #4) disappears because
the note becomes one self-contained document.

Production data already exists and must **not be lost** — existing notes are
recycled in place into the new shape.

## Decisions locked (with the user)

- **#3 Artifact shape:** one note → one `DailyNoteArtifact` JSON document with
  pages embedded as nested children. No separate `NotePageArtifact` rows minted.
- **Synthesis altitude:** one **note-level** coherent synthesis; children stay
  **raw-only** (faithful extraction). Synthesis is the "strong semantic" layer.
- **#1 Personality — silent corrector:** synthesis NEVER emits wrong math. If a
  note is wrong, climb one level up the logical tree, infer intent, silently
  produce the correct version. Never reproduce the error, never flag it. Safe
  because the raw extraction is preserved in the children (evidence never lost).
- **Migration = Recycle:** reuse each note's stored transcript + page text, run
  ONLY the new synthesis pass, rewrite the note **in place (same `artifact_id`)**.
  No re-transcribe / re-vision.
- **Old `note_page` rows:** **leave them** (non-destructive). Keep the
  `NotePageArtifact` class registered for back-compat reads + as the migration's
  data source; just stop minting new ones.

## Key platform facts driving the design (verified)

- Artifacts are one JSONB `payload` per row keyed by `artifact_id`;
  `ArtifactService.put()` is an **upsert** (`ON CONFLICT DO UPDATE`). Reusing an
  id rewrites in place → idempotent migration.
  (`ai-platform/.../jobs/artifact_service.py`, `supabase/migrations/0001_initial.sql`)
- `BaseArtifact` is `extra="forbid"` and reads `model_validate` against the
  **current** class; list ops **silently skip** rows that fail to hydrate. ⇒ the
  new schema MUST be **additive** (new fields optional w/ defaults) so old rows
  still hydrate and never vanish from lists. (`ai-platform/.../jobs/artifact.py`)
- Media blobs are retained indefinitely & re-downloadable; old
  `DailyNoteArtifact.transcript` + `NotePageArtifact.text` are already-extracted
  raw text the migration can recycle. (`ai-platform/.../jobs/media_service.py`)
- A standalone script can build the service directly:
  `ArtifactService(make_backend().artifact_repo, registry=MATH_NOTES_ARTIFACTS)`
  then `.query(...)` / `.put(...)`. (`ai-platform/.../workspace/bootstrap.py`,
  `.../workspace/storage/backends.py`)

---

## Part A — Pipeline + schema redesign (the live ingest)

### A1. Artifact schema — additive (no field removals)
File: `packages/math-notes/src/mathai/math_notes/artifacts.py`

- New nested `BaseModel`s (NOT artifact types):
  - `NotePage`: `page_index`, `image_ref`, `raw_text: Optional[str]`,
    `diagram_description: Optional[str]`. (Faithful per-photo extraction; this is
    the stored child — supersedes `ParsedPage`'s storage role.)
  - `NoteSynthesis`: `markdown: Optional[str]` (prose + embedded KaTeX,
    document-mode validated), `concepts: list[str]`, `summary: Optional[str]`,
    `model_used: Optional[str]`, `validation_attempts: int = 0`.
- `DailyNoteArtifact` gains (all optional/defaulted so OLD rows still hydrate):
  - `pages: list[NotePage] = []`
  - `synthesis: Optional[NoteSynthesis] = None`
  - `schema_version: int = 1`  ← old rows default to 1; new/migrated rows = 2
    (the migration's idempotency marker).
  - **Keep** all existing fields (`note_date`, `created_by`, `image_refs`,
    `transcript`, `ocr_text`, blob refs) — removing any would break old-row reads.
- **Keep** `NotePageArtifact` in `MATH_NOTES_ARTIFACTS` (registered for
  back-compat + migration source); just stop minting it.

### A2. Graph: Transcribe → Extract → Synthesize → End
Files: `workflow.py`, `state.py`, `execution.py`

- `TranscribeNoteStep` — unchanged (faithful audio transcript).
- `ParsePagesStep` → **extraction-only**: vision helper prompted for a *faithful
  transcription only* (no JSON/LaTeX/concepts). Produces `NotePage{raw_text,
  diagram_description}` per photo. **Remove** the per-page `validate_latex` agent
  loop and the JSON `_coerce_page` concept parsing.
- **New `SynthesizeNoteStep`**: gathers `transcript` + all `pages[].raw_text`,
  runs ONE Opus agent (silent-corrector persona) → `NoteSynthesis`, then a single
  `validate_latex` compile loop in `mode="document"` over the synthesized
  markdown (KaTeX compile guarantee — reuse `tools.validate_latex`).
- Factor the synthesis into a **reusable function**
  `synthesize_note(transcript, pages, instructions) -> NoteSynthesis` so both the
  live node AND the migration script call the same code (DRY).
- `MathNotesState`: add `pages: list[NotePage]`, `synthesis: Optional[NoteSynthesis]`.
- `_persist` (execution.py): mint ONE `DailyNoteArtifact` with `pages` +
  `synthesis` + `schema_version=2`; drop the per-page `NotePageArtifact` loop.
- `_extract_math_notes_result` / `models.py`: result preview reflects the new
  note shape (note carries `synthesis`).

### A3. Prompts (domain-owned, registry-loaded — pattern already in place)
Files: `packages/math-notes/instructions/*`, `execution.py` deps_factory

- Rewrite `page_parse.md` → **faithful-extraction-only** (transcribe the page;
  no math JSON). Prompt name stays `math_notes.page_parse`.
- New `synthesis.md` (`math_notes.synthesis`) — the silent-corrector personality
  + the `validate_latex` document-loop instructions.
- `latex_render.md` folds into `synthesis.md` (remove the file; an orphaned
  registry entry is harmless). `tools.py validate_latex` stays.
- `deps_factory` loads `math_notes.page_parse` + `math_notes.synthesis` via the
  existing best-effort `_load_prompt` (PlatformClient.prompt_registry).

### A4. UI (math-ui)
Files: `math-ui/lib/domains/math-notes/types.ts`, `math-ui/app/math-notes/page.tsx`

- `types.ts`: `DailyNoteArtifact` now exposes `pages` + `synthesis`; the separate
  `NotePageArtifact` type/fetch is removed.
- `page.tsx` `loadNotes`: **drop the per-note `note_page` query** (kills the
  N+1) — one `fetchArtifactsFull({ artifactType: "daily_note" })` returns
  everything. Render `note.synthesis` (markdown via `Latex`) as the primary view;
  keep raw `note.pages` available (e.g. collapsible "what you wrote").
- Regenerate SDK types after the schema deploys (`npm --prefix math-ui update
  @sepoul-packages/sdk` once the platform releases, or local OPENAPI regen).

---

## Part B — Migration "side thread" (recycle, in place, idempotent, tracked)

A robust, committed, resumable batch script — built to **not die silently**:
structured logs, a written report, per-note isolation, idempotent re-runs.

File (new): `packages/math-notes/scripts/migrate_notes_to_document.py`

Algorithm:
1. Build `ArtifactService(make_backend().artifact_repo,
   registry=MATH_NOTES_ARTIFACTS)`. (Direct backend access, as platform's own
   `scripts/migrate_backend.py` does.)
2. Enumerate `service.list_by_type("daily_note")`.
3. **Idempotent skip**: `if note.schema_version >= 2: skip` (re-runs only retry
   the not-yet-migrated / previously-failed).
4. Gather children: `service.query(artifact_type="note_page",
   fields={"source_note_id": str(note.artifact_id)})` → build `NotePage`
   children (`raw_text` from old `NotePageArtifact.text`, `diagram_description`).
   Audio-only notes → `pages=[]`.
5. `synthesize_note(note.transcript, pages, instructions)` — the SAME domain
   function (1 Opus call/note). `validate_latex` needs `UI_TOOL_API_URL`
   reachable.
6. Set `note.pages`, `note.synthesis`, `note.schema_version = 2`;
   `service.put(note)` → in-place overwrite (same `artifact_id`, `created_at`).
7. **Leave** old `note_page` rows untouched.

Robustness / "keep tracking it":
- `argparse`: `--dry-run` (default, no writes) / `--apply`, `--limit`,
  backend via env (`BACKEND`, `SUPABASE_*` / `LOCAL_DATA_DIR`).
- Per-note `try/except` → one failure never aborts the batch.
- Structured logging + a written `migration-report.json` (per-note
  migrated/skipped/failed + reason; totals). Re-run is the retry mechanism.
- Runs in the **default-runtime venv** (needs `basic_agent`/Anthropic) with the
  platform `src` on `PYTHONPATH` (per CLAUDE.md), pointed at the target backend.

---

## Reused code (don't rebuild)
- `tools.validate_latex` (KaTeX compile loop) — `packages/math-notes/src/mathai/math_notes/tools.py`
- `ai_platform.ai.providers.basic_agent.basic_agent` (Anthropic agent)
- `ai_platform.ai.providers.{audio,vision}` interpreters (extraction)
- `ArtifactService` / `make_backend()` / `PlatformSession` (platform)
- Prompt-registry loader pattern already wired in `execution.py` (`_load_prompt`)

## Deploy / ops sequence
1. Implement Part A (schema additive, pipeline, prompts) + Part B script.
2. Bump version in `pyproject.toml` + `bundle.toml`; `uv build --wheel`;
   `aiplatform deploy`; `aiplatform deploy-prompts`.
3. `docker restart ai-platform-worker-1` (load the new wheel).
4. SDK regen → math-ui types + render update.
5. Migration: `--dry-run` (review report) → `--apply` → re-run (confirm all skip).

## Verification (end-to-end)
- **New note:** capture audio + photos → exactly ONE `daily_note` artifact with
  `pages` (raw) + `synthesis` (validated markdown), `schema_version=2`, and NO
  `note_page` artifact minted. Confirm `validate_latex` compiled the synthesis.
- **Additive safety:** before running the migration, old notes still appear in
  `GET /artifacts?artifact_type=daily_note` (hydrate with `synthesis=null`) —
  proves no silent disappearance.
- **Migration:** dry-run report lists candidates; `--apply` migrates; re-run
  reports all skipped (idempotent). Spot-check a migrated note: same
  `artifact_id`, `synthesis` populated, `pages` embedded, original `note_page`
  rows still present.
- **UI:** renders `synthesis` + collapsible raw pages; network shows a single
  artifacts fetch (no per-note N+1).
- Tests: extend `packages/math-notes` tests for the new graph (synthesis node,
  additive hydration of an old-shape payload) + a migration unit test over a
  `LocalArtifactRepository` fixture (old daily_note + note_page → migrated doc).

## Out of scope (tracked separately)
- iPhone ~3MB photo upload usability bug → memory `daily-notes-image-upload-bug`
  (client-side downscale before upload). Not part of this change.
- Exact Opus model id / cost for the synthesis agent: load the `claude-api`
  skill before wiring `basic_agent`, so the model + cost are accurate.

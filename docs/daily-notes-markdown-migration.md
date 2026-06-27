# Daily Notes — Markdown + `$`-delimited math migration (hand-off plan)

> Plan for the CLAUDE.md "NEXT topic". Self-contained — hand it to a fresh
> session. Goal: `daily_note.synthesis.markdown` moves from KaTeX-delimited
> LaTeX (`\(...\)` / `\[...\]`) to canonical Markdown + `$`/`$$` math, rendered
> as real Markdown (headings/bold/lists) instead of literal `##`.

## ⟶ Does this need ai-platform (platform) changes? **NO.**

Everything is **domain-side (this repo)**. The schema is unchanged —
`synthesis.markdown` stays a `str` — so there is **no `ArtifactType` change, no
SDK regen, no platform deploy**, and (notably) **no `deploy-before-migrate`
coupling** like the v1→v2 redesign had (that one added fields; this one only
edits string *content*). Concretely the work is:

- a domain data-migration **script** (uses the existing `ArtifactService` — same
  as `scripts/migrate_notes_to_document.py`),
- a **prompt** edit (`instructions/synthesis.md`) shipped via `deploy-prompts`,
- a **math-ui** change (the validate-latex route regex + a Markdown renderer + 2
  npm deps).

**No math-notes wheel rebuild is needed either** (the prompt is registry-loaded;
the `validate_latex` *tool* is a thin HTTP client and doesn't change — only the
math-ui route's regex does). Rollout is unusually light (see §Rollout).

---

## Current state (verified — file pointers)

- **Storage:** `DailyNoteArtifact.synthesis: Optional[NoteSynthesis]`,
  `NoteSynthesis.markdown: Optional[str]` —
  `packages/math-notes/src/mathai/math_notes/artifacts.py`. One JSONB payload
  per row; `ArtifactService.put()` is an upsert by `artifact_id`.
- **Synthesis prompt:** `packages/math-notes/instructions/synthesis.md`, loaded
  from the **prompt registry** at run time (`_load_prompt("math_notes.synthesis")`
  in `execution.py`). It currently instructs `\(...\)` inline / `\[...\]` display.
  ⚠️ **This file is also edited by open PR #9 (flairs)** — it has a
  `LEARNER DIRECTIVES` carve-out. Rebase: keep that, change only the math rules.
- **Validation:** `validate_latex` tool
  (`packages/math-notes/src/mathai/math_notes/tools.py`) is a thin client that
  POSTs the whole markdown `{latex, mode:"document"}` to math-ui. **The split
  happens in math-ui**, not the tool.
  - `math-ui/app/api/tools/validate-latex/route.ts`:
    `SEGMENT_RE = /\\\((.+?)\\\)|\\\[([\s\S]+?)\\\]/g` — **only `\(...\)`/`\[...\]`.**
    ❗ If synthesis emits `$...$` and this regex isn't updated, document-mode
    finds no segments and returns *trivially valid* → **new notes silently skip
    KaTeX validation.** Must update this regex.
- **Frontend render:** `math-ui/components/notes/note-view.tsx:35` renders
  `synthesis.markdown` via `<Latex>` (`components/library/latex.tsx`) — a custom
  regex splitter that does math but **does not parse Markdown structure** (so
  `##`, `**bold**`, lists render literally).
  - `<Latex>` is **also used by** `app/latex/page.tsx`, `artifact-card.tsx`,
    `review-form.tsx`, `result-display.tsx`, `conversation-bubble.tsx`. **Do NOT
    delete it** — only swap the NoteView synthesis usage.
- **Deps:** `react-markdown@^10`, `remark-gfm@^4`, `katex@^0.16` present;
  **`remark-math` + `rehype-katex` MISSING** (must add).
- **Migration precedent to mirror:** `scripts/migrate_notes_to_document.py`
  (ArtifactService over `make_backend()`, `--apply` default-dry-run, JSON report,
  per-note try/except, idempotent skip). Run recipe in CLAUDE.md / that script's
  docstring (default-runtime venv, `BACKEND`/`SUPABASE_SCHEMA`, `PYTHONPATH`).

---

## Plan

### Part 1 — In-place delimiter migration (existing notes)
New script `packages/math-notes/scripts/migrate_synthesis_delimiters.py`,
modeled on `migrate_notes_to_document.py`:

- Build `ArtifactService(make_backend().artifact_repo, registry=MATH_NOTES_ARTIFACTS)`.
- `for note in service.list_by_type("daily_note")`: if `note.synthesis` and
  `note.synthesis.markdown` is a non-empty `str`, replace **independently**:
  `\(`→`$`, `\)`→`$`, `\[`→`$$`, `\]`→`$$`. Leave every other field untouched.
  Skip notes with no `synthesis.markdown`.
- `service.put(note)` (upsert, same `artifact_id`/`created_at`).
- **Idempotent:** after the first pass there are no `\(`/`\)`/`\[`/`\]` left, so a
  re-run changes nothing. (Notes already in `$` form → no-op.)
- `--apply` (default dry-run) + `--report` JSON + counts (scanned/updated/
  skipped/failed-with-ids) + per-note try/except (one failure never aborts).
- No schema change ⇒ runnable against any deployed version; no version coupling.

### Part 2 — Future synthesis emits `$`-delimited Markdown
Edit `packages/math-notes/instructions/synthesis.md`:

- Replace the math-format rules with: *Write clean GitHub-style Markdown.
  Inline math `$...$`; display math `$$...$$` with the `$$` delimiters on their
  own lines. Never use `\(...\)`, `\[...\]`, raw HTML, Unicode super/subscripts,
  or math fragmented across lines. Keep TeX valid and readable.* (Target shape =
  the Cosets example in CLAUDE.md's NEXT topic.)
- Update the `validate_latex` instruction line: it says "splits on the math
  delimiters" — restate the delimiters as `$...$` / `$$...$$`.
- **Preserve PR #9's `LEARNER DIRECTIVES`/flair carve-out** verbatim.
- Ship via `aiplatform deploy-prompts --bundle packages/math-notes/bundle.toml`.
  Registry-loaded per job → **no wheel rebuild, no worker restart** (a restart
  only if you want to drop any prompt cache).

### Part 3 — Frontend: real Markdown + KaTeX, and fix the validate regex
1. **Validate route** (`math-ui/app/api/tools/validate-latex/route.ts`): widen
   `SEGMENT_RE` to also match `$$...$$` and `$...$` (mirror the pattern already in
   `components/library/latex.tsx`: `$$` before `$`; the inline `$` form requires a
   non-`$`/newline interior to avoid `"$5 and $10"` false positives). This keeps
   **both** old `\(...\)` (only relevant if a note dodged the migration) and new
   `$...$` validating. math-ui-only; no wheel.
2. **Deps:** `npm --prefix math-ui i remark-math rehype-katex`.
3. **Renderer:** add `math-ui/components/library/markdown-math.tsx` (or extend
   `components/library/markdown.tsx`): `ReactMarkdown` with
   `remarkPlugins={[remarkMath, remarkGfm]}`, `rehypePlugins={[rehypeKatex]}`,
   reuse the existing `Markdown` `COMPONENTS` map (Tailwind headings/bold/lists —
   preserve current typography), `import "katex/dist/katex.min.css"` once. **No
   `dangerouslySetInnerHTML`** (react-markdown handles it).
4. **Swap** `note-view.tsx`: render `synthesis.markdown` via `<MarkdownMath>`
   instead of `<Latex>`. Leave the transcript + raw-page `<details>` views as
   plain text. **Keep `<Latex>` for its other call sites.**

### Part 4 — Tests (if/where infra exists)
- **Migration unit test** over a `LocalArtifactRepository` fixture: a note with
  `\(...\)`/`\[...\]` → `$...$`/`$$...$$`; re-run = no change (idempotent); a note
  with no `synthesis.markdown` untouched. (Mirror any existing math-notes test.)
- **Frontend:** headings/bold render as semantic HTML; inline + display TeX
  render through KaTeX (`.katex` in output). math-ui test infra is thin — add
  only if present; otherwise a manual check on a migrated note.

---

## Rollout (light — no platform, no wheel)
1. Land Parts 1–4 in one math-app PR.
2. `aiplatform deploy-prompts …` (Part 2 prompt).
3. Run the migration: `--dry-run` → review report → `--apply` (Part 1).
4. Deploy math-ui (Part 3 + validate regex) — merge → GHCR rebuild → `redeploy.sh`.
   (No `aiplatform deploy`, no worker restart, no SDK regen.)
5. **Verify:** a migrated note renders real headings/bold + inline & display
   math; a freshly-captured note's `synthesis.markdown` comes back `$`-delimited
   **and** `validate_latex` actually validated it (check the regex change landed —
   the route should report segments, not "no delimiters").

## Gotchas / interactions
- **PR #9 (flairs)** touches `synthesis.md` too — rebase, keep the flair block.
- **The validate-route regex is the easy thing to forget** — miss it and new
  notes pass validation without their math ever being checked.
- `<Latex>` stays (other surfaces). Only NoteView's synthesis swaps to Markdown.
- Platform untouched; schema untouched; `synthesis.markdown` stays a `str`.

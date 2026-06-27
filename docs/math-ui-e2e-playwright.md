# math-ui E2E with Playwright — two-part smoke suite (hand-off plan)

> Replace manual UI click-testing with a **minimal** Playwright smoke suite —
> *not* exhaustive. **Two parts:**
> 1. **Mock smoke** — fast, deterministic, no backend; guards UI rendering/behavior.
> 2. **Live smoke** — a couple of *real* end-to-end journeys against the live
>    local stack, covering the main domain features.
>
> Self-contained — hand to a fresh session (implement → PR → review, like the
> markdown-latex work). Run **manually during local dev**.

## ⟶ Platform changes? **No.** math-ui packaging changes? **No.**
- No ai-platform changes. No changes to `math-ui/package.json` or its Docker image.
- Lives in a **separate top-level `e2e/` package** (own `package.json` / config /
  `node_modules`); the math-ui build context is `math-app/math-ui/`, so `e2e/` is
  invisible to it. **Manual runs only; not wired into CI.**

## One package, two Playwright *projects*
`playwright.config.ts` defines two projects so you choose your speed:
- **`mock`** — runs anytime, needs only `npm run dev` (no platform stack). BFF
  calls are intercepted with `page.route('**/api/**', …)` → fixture JSON.
- **`live`** — needs the rolled local stack; its `globalSetup` health-checks the
  stack and **skips with a clear message** if it's down (so a `mock`-only run
  never fails for missing backend).

```bash
npx playwright test --project=mock     # fast, deterministic, no backend (default dev loop)
npx playwright test --project=live     # the real elephant: real jobs + Opus/OpenAI (minutes)
```

## Layout (new — all under `math-app/e2e/`)
```
e2e/
  package.json            # @playwright/test devDep only
  playwright.config.ts    # projects: mock (no setup) + live (globalSetup health-check)
  README.md               # run instructions + how to make the audio fixture
  support/
    mock.ts               # mockPlatform(page, fixtures) → page.route for /api/artifacts|jobs|media
    stack.ts              # live helpers: assertStackUp(), waitForNoteInHistory(), cleanup()
  fixtures/
    artifacts.ts          # mock fixtures: dailyNote({synthesis, pages, transcript, image_refs})
    voice-note.m4a        # real ~15s math voice note  (live)
    page-cosets.jpg       # real photo/screenshot of math  (live)
  tests/
    mock/
      rendering.smoke.ts        # the markdown/KaTeX regression guard
      daily-notes.smoke.ts      # history + detail + flair-submit
      routes.smoke.ts           # every route loads, no console errors
    live/
      notes-capture.live.ts     # real math_notes journey
      math-qa.live.ts           # real math_qa journey
```
`.gitignore` (repo root): `e2e/node_modules/`, `e2e/test-results/`, `e2e/playwright-report/`, `e2e/.last-run.json`.

---

## Part 1 — Mock smoke (fast, no backend)
The daily-notes pages fetch the BFF (`/api/artifacts*`, `/api/jobs*`, `/api/media*`)
**from the browser**, so `page.route` intercepts them and returns fixtures. Keep
it to a few high-value smokes:

- **`rendering.smoke.ts`** — *the_ reason this exists. Mock a `daily_note` whose
  `synthesis.markdown` has `## heading`, `**bold**`, a list, `$inline$`, and a
  `$$display$$` block; open `/math-notes/<id>` and assert real `<h2>` / `<strong>`
  / `<li>`, **`.katex`** (inline) + **`.katex-display`**, and **no literal**
  `##`/`$$`/`**` in the text. Fails if the `MarkdownMath` swap regresses.
- **`daily-notes.smoke.ts`** — mock a small list → `/math-notes` shows the cards
  (date, preview, badges, photo-count) and the empty state with no fixtures;
  mock the record page, toggle **"Don't spoil"**, Save, and assert the
  intercepted `…/jobs/runs/submit` body carries `flairs:["dont_spoil"]`.
- **`routes.smoke.ts`** — visit each nav route with a permissive `/api` mock;
  assert the `PageHeader` renders and **no uncaught console errors**.

`mockPlatform(page, …)` handlers: `/api/artifacts?…full=true` → `{artifacts,total}`;
`/api/artifacts/<id>` → one artifact (or 404 for the miss case); `/api/jobs/runs/submit`
→ `{job_id,status:'PENDING'}` (capture body); `/api/jobs/<id>` → `SUCCEEDED`;
`/api/media/**` → a 1×1 PNG so `<img>`/`<audio>` don't error.

## Part 2 — Live smoke (real stack, main features)
Real captures → real jobs → assert what the UI actually renders. **Minimal: one
journey per main feature.** `globalSetup` first asserts: `:8000/health` 200,
`/job-definitions` lists the 3 domains, `:3000` up, and (warns if not) the worker's
`UI_TOOL_API_URL` points at the host UI (`http://host.docker.internal:3000`) so
`validate_latex` runs.

- **`notes-capture.live.ts`** — `goto('/math-notes/record')`, `setInputFiles` the
  **audio fixture** on the *"or choose a file"* input (drive the file path, not
  the mic) + `page-cosets.jpg` on a photo input, Save. Then **wait on the end
  state** (`waitForNoteInHistory`, ~240s — the job can outlast the record page's
  own poll, but it still completes), open the note, and assert **structurally**:
  synthesis renders as Markdown + KaTeX (heading/strong/`.katex`, no literal
  `##`/`$$`), audio player + photo thumbnail present, "What you wrote" reveals the
  transcript. Don't assert exact synthesis text (model output).
- **`math-qa.live.ts`** — ask a question on `/`, wait for the result view, assert
  the answer renders (and `.katex` if it produced LaTeX). Real Opus.

Config for `live`: `workers:1` (one shared stack), `retries:0` (don't double-spend
LLM calls), `timeout:240_000`, `trace/video:'retain-on-failure'`.

**Cleanup:** captures mint real `daily_note`/`note_page` rows in the `test`
schema. Simplest: accept accumulation (it's the dev schema; the integration suite
truncates it anyway). Optional: an `afterAll` that deletes the ids it created via
a tiny `search_path=test` psycopg helper (no artifact DELETE API exists).

---

## How to run (README content)
```bash
cd e2e && npm install && npx playwright install chromium
# Part 1 (anytime, just needs the dev server):
npm --prefix ../math-ui run dev   # in another terminal (or let webServer start it)
npx playwright test --project=mock
# Part 2 (needs the rolled local stack on :8000 + dev server):
npx playwright test --project=live
npx playwright test --ui          # iterate
npx playwright show-report
```
README also notes how to make `voice-note.m4a` (e.g. macOS `say … -o x.aiff` →
`afconvert`/`ffmpeg` to m4a, or a real <20s clip — keep it short and math-y).

## Verification (definition of done)
- `--project=mock` is green with only the dev server up; `rendering.smoke.ts`
  fails if the renderer regresses to literal `##`/`$$` (the guard that motivated this).
- `--project=live` `notes-capture` goes green against the rolled stack: a real
  captured note renders markdown+KaTeX; `math-qa` returns a rendered answer.
- Diff touches only `e2e/**`, `.gitignore`, and — *optionally* — a couple of
  `data-testid`s on `note-view.tsx`/`markdown-math.tsx` if role/text selectors get
  brittle. math-ui's package/build/image unchanged.

## Out of scope (keep it smoke)
- Exhaustive case matrices, CI wiring, visual snapshot baselines, parallel live
  runs, asserting exact model output. Minimal smoke now; grow later if wanted.

# math-ui E2E — Playwright smoke suite

A **minimal** smoke suite for `math-ui` (not exhaustive). Two Playwright
*projects*, two speeds:

- **`mock`** — fast, deterministic, **no platform stack**. Every BFF `/api/**`
  call is intercepted with `page.route` and answered from fixtures
  (`support/mock.ts`). This is the default dev loop and the regression guard for
  the Markdown + KaTeX render path.
- **`live`** — the real elephant: real captures → real jobs → real Opus/OpenAI
  (minutes). Needs the rolled local stack on `:8000`. Each live spec
  health-checks the stack in `beforeEach` and **skips with a clear message** if
  it's down, so a `mock`-only run never fails for a missing backend.

This package is **standalone** (its own `package.json` / `node_modules` /
config) and lives outside the `math-ui/` build context, so it's invisible to the
`math-ui` image. **Manual runs only — not wired into CI.**

## Setup

```bash
cd e2e
npm install
npx playwright install chromium
```

## Run

The `webServer` in `playwright.config.ts` starts (or reuses) the math-ui dev
server on `:3000` automatically, so you don't have to start it yourself.

```bash
# Part 1 — mock (anytime; no backend):
npx playwright test --project=mock        # or: npm run test:mock

# Part 2 — live (needs the rolled stack on :8000 + real LLM spend):
npx playwright test --project=live        # or: npm run test:live

npx playwright test --ui                  # iterate interactively
npx playwright show-report                # last HTML report  (npm run report)
```

Overrides: `MATH_UI_URL` (default `http://localhost:3000`) and `MATH_API_URL`
(default `http://localhost:8000`).

## What each spec covers

```
tests/mock/
  rendering.smoke.ts     # THE guard: synthesis.markdown → real <h2>/<strong>/<li> + .katex
                         #            (+ no literal ## / $$ / ** leaking through)
  daily-notes.smoke.ts   # history cards, empty state, record-page "Don't spoil" → submit body
  routes.smoke.ts        # every nav route renders its <h1> with no uncaught errors
tests/live/
  notes-capture.live.ts  # real audio+photo capture → note renders markdown/KaTeX, audio, photo, transcript
  math-qa.live.ts        # real question → rendered answer
```

## Live fixtures

`fixtures/voice-note.m4a` (a short, clear math voice note) and
`fixtures/page-cosets.jpg` (an image of hand-note math) are **committed**, so
running the suite needs no extra tooling. To regenerate them (macOS — uses
`say` + `afconvert`; the image needs `python3` + Pillow):

```bash
npm run fixtures            # node scripts/make-fixtures.mjs
```

Keep any replacement short (<20s) and math-y so transcription + synthesis stay
quick. For the live notes journey to validate LaTeX, the default worker's
`UI_TOOL_API_URL` must point at the host UI (`http://host.docker.internal:3000`);
the live guard prints a reminder.

## Scope

Smoke only. No exhaustive case matrices, CI wiring, visual snapshot baselines,
parallel live runs, or asserting exact model output. Grow later if wanted.

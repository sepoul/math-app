import { defineConfig, devices } from "@playwright/test";

/**
 * math-ui smoke suite — two projects, two speeds (see README.md):
 *
 *   mock  — fast, deterministic, no platform stack. BFF `/api/**` calls are
 *           intercepted with `page.route` and answered from fixtures
 *           (`support/mock.ts`). Runs anytime the dev server is up.
 *   live  — the real elephant: real captures → real jobs → real Opus/OpenAI.
 *           Needs the rolled local stack on :8000. Each live spec guards with
 *           `skipUnlessStackUp()` (support/stack.ts), so a `mock`-only run
 *           never fails for a missing backend.
 *
 *   npx playwright test --project=mock     # default dev loop
 *   npx playwright test --project=live     # minutes; real LLM spend
 *
 * `webServer` starts (or reuses) the math-ui dev server on :3000. It does NOT
 * start the platform stack — that's operator-driven (../ai-platform compose).
 */
const BASE_URL = process.env.MATH_UI_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./tests",
  // Files are named *.smoke.ts / *.live.ts, not the default *.spec.ts.
  testMatch: /.*\.(smoke|live|spec|test)\.ts$/,
  // Don't run mock + live against the same shared stack/server in parallel.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  reporter: [["list"], ["html", { open: "never" }]],

  webServer: {
    command: "npm --prefix ../math-ui run dev",
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
  },

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },

  projects: [
    {
      name: "mock",
      testDir: "./tests/mock",
      retries: 1,
      timeout: 60_000,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "live",
      testDir: "./tests/live",
      // One shared stack; never run live specs in parallel and never retry —
      // a retry would double-spend the LLM calls.
      workers: 1,
      retries: 0,
      // Real ASR + vision + Opus synthesis can run minutes; give it headroom
      // over the per-step waits in the specs.
      timeout: 300_000,
      use: {
        ...devices["Desktop Chrome"],
        video: "retain-on-failure",
      },
    },
  ],
});

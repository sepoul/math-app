import { test, expect } from "@playwright/test";
import { mockPlatform } from "../../support/mock";

/**
 * Every nav route loads against a permissive `/api` mock: the `PageHeader`
 * (an `<h1>`) renders and nothing throws an uncaught exception. Cheap guard
 * that a route didn't break its data wiring or crash on first paint.
 */
const ROUTES = [
  "/",
  "/math-qa",
  "/math-notes",
  "/math-conversation",
  "/workflows",
  "/jobs",
  "/artifacts",
  "/artifact-types",
  "/latex",
  "/figures",
];

// Dev-server resource/network chatter that isn't an app bug.
const NOISE = [/favicon/i, /Failed to load resource/i, /net::ERR_/i, /React DevTools/i];

for (const route of ROUTES) {
  test(`route ${route} renders its header with no uncaught errors`, async ({ page }) => {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      if (!NOISE.some((re) => re.test(text))) consoleErrors.push(text);
    });

    await mockPlatform(page, {});
    await page.goto(route);

    await expect(page.locator("h1").first()).toBeVisible();

    expect(pageErrors, `uncaught exceptions on ${route}`).toEqual([]);
    expect(consoleErrors, `console errors on ${route}`).toEqual([]);
  });
}

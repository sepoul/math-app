import { test, expect } from "@playwright/test";
import { mockPlatform } from "../../support/mock";
import { dailyNote, sectionedNote } from "../../fixtures/artifacts";

/**
 * The reason this suite exists: guard the `daily_note.synthesis.markdown`
 * render path (`MarkdownMath` = react-markdown + remark-math + rehype-katex).
 * A regression to literal/plain-text rendering would leak the `##` / `$$` /
 * `**` delimiters into the visible text and drop the KaTeX nodes — this fails
 * loudly on exactly that.
 */
test("daily note synthesis renders as Markdown + KaTeX, not raw delimiters", async ({ page }) => {
  const note = dailyNote({ artifact_id: "render-note" });
  await mockPlatform(page, { notes: [note] });

  await page.goto("/math-notes/render-note");

  // Real Markdown structure (not literal markup).
  await expect(page.locator("h2", { hasText: "Cosets and Lagrange" })).toBeVisible();
  await expect(page.locator("strong", { hasText: "left cosets" })).toBeVisible();
  expect(await page.locator("li").count()).toBeGreaterThanOrEqual(2);

  // KaTeX: inline ($…$) and a display ($$…$$) block.
  expect(await page.locator(".katex").count()).toBeGreaterThanOrEqual(1);
  await expect(page.locator(".katex-display").first()).toBeVisible();

  // None of the delimiters survive into the rendered text.
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("$$");
  expect(text).not.toContain("##");
  expect(text).not.toContain("**");
});

/**
 * The enriched (epic #14 / S6) render path: a sectioned, magnitude-aware note
 * shows one navigable `<section>` per topic + a depth/magnitude badge, with
 * per-section KaTeX still rendered. Guards the structure the richer synthesis
 * unlocked — if the UI regressed to the single flat blob, the section headings,
 * the topic nav, and the badge would all vanish.
 */
test("sectioned note renders navigable sections + a magnitude badge", async ({ page }) => {
  const note = sectionedNote({ artifact_id: "sectioned-note" });
  await mockPlatform(page, { notes: [note] });

  await page.goto("/math-notes/sectioned-note");

  // Both topical headings render (as real <h2> structure).
  await expect(
    page.locator("h2", { hasText: "Cosets and Lagrange" })
  ).toBeVisible();
  await expect(page.locator("h2", { hasText: "The chain rule" })).toBeVisible();

  // The topic nav links resolve to the per-section anchors.
  const nav = page.getByRole("navigation", { name: "Sections" });
  await expect(nav).toBeVisible();
  await expect(nav.locator('a[href="#note-section-1"]')).toBeVisible();
  await expect(nav.locator('a[href="#note-section-2"]')).toBeVisible();
  await expect(page.locator("#note-section-1")).toBeVisible();
  await expect(page.locator("#note-section-2")).toBeVisible();

  // The magnitude/depth badge: depth tier + topic count.
  await expect(page.getByText("deep · 2 topics")).toBeVisible();

  // Per-section concept chips from each section (exact, so they don't also
  // match the headings that contain these words as substrings).
  await expect(page.getByText("Lagrange's theorem", { exact: true })).toBeVisible();
  await expect(page.getByText("Chain rule", { exact: true })).toBeVisible();

  // KaTeX still renders per section (inline $…$ and a display $$…$$).
  expect(await page.locator(".katex").count()).toBeGreaterThanOrEqual(1);
  await expect(page.locator(".katex-display").first()).toBeVisible();

  // No raw delimiters leak from any section's markdown.
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("$$");
  expect(text).not.toContain("**");
});

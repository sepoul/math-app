import { test, expect } from "@playwright/test";
import { mockPlatform } from "../../support/mock";
import { dailyNote } from "../../fixtures/artifacts";

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

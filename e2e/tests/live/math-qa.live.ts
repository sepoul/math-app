import { test, expect } from "@playwright/test";
import { skipUnlessStackUp } from "../../support/stack";

test.beforeEach(skipUnlessStackUp);

/**
 * Real math_qa journey: ask a question on the home page, follow the redirect to
 * the job page, and assert the answer renders (real Opus). math_qa pauses at a
 * human-review gate before it finishes, so the smoke also clears the gate
 * (fills + submits the review) and then asserts the final result view. The
 * `.or()` keeps it robust if a config ever auto-runs without the gate.
 */
test("ask a question, clear the review gate, and get a rendered answer", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("Math question").fill("What is the derivative of x squared?");
  await page.getByRole("button", { name: /ask ai/i }).click();

  await page.waitForURL(/\/math-qa\/[^/]+$/, { timeout: 15_000 });

  // Either the review gate (answer + review form) or the final result appears.
  const reviewBtn = page.getByRole("button", { name: /submit review/i });
  const finalAnswer = page.getByText("AI Answer");
  await expect(reviewBtn.or(finalAnswer)).toBeVisible({ timeout: 200_000 });

  // The generated answer is rendered at this point (Confidence badge only shows
  // when the ai_response is present).
  await expect(page.getByText(/Confidence:/).first()).toBeVisible();

  // Clear the review gate so the job proceeds to its terminal result view.
  if (await reviewBtn.isVisible()) {
    await page.locator("#comment").fill("Clear, correct steps.");
    await reviewBtn.click();
    await expect(finalAnswer).toBeVisible({ timeout: 120_000 });
  }

  const katex = page.locator(".katex");
  if (await katex.count()) await expect(katex.first()).toBeVisible();
});

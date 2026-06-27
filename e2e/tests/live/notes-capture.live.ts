import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { skipUnlessStackUp, latestNote, waitForNewNote } from "../../support/stack";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures");

// Skip (don't fail) the whole journey if the platform stack isn't up.
test.beforeEach(skipUnlessStackUp);

/**
 * Real math_notes journey: drive the file inputs (audio + photo) on the record
 * page, hit Save, then wait for the minted note independently of the record
 * page's own poll (the synthesis pass can outlast it). Assert the note renders
 * structurally — Markdown + KaTeX, audio, photo, transcript — never exact text.
 */
test("capture a real note renders Markdown + KaTeX, audio, photo, transcript", async ({
  page,
  request,
}) => {
  const baseline = await latestNote(request);

  await page.goto("/math-notes/record");
  await page.setInputFiles('input[accept="audio/*"]', join(FIX, "voice-note.m4a"));
  await page.setInputFiles('input[accept="image/*"][multiple]', join(FIX, "page-cosets.jpg"));

  // Photo preview appears once the client-side downscale finishes.
  await expect(page.locator('img[alt^="photo"]').first()).toBeVisible();

  const save = page.getByRole("button", { name: /save note/i });
  await expect(save).toBeEnabled();
  await save.click();

  const id = await waitForNewNote(request, baseline?.created_at ?? null, {
    timeoutMs: 220_000,
  });

  await page.goto(`/math-notes/${id}`);

  // Synthesis renders as Markdown + KaTeX (no raw delimiters), not plain text.
  await expect(page.locator(".katex").first()).toBeVisible({ timeout: 15_000 });
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("$$");
  expect(text).not.toContain("##");

  // Audio player + photo thumbnail present.
  await expect(page.locator("audio")).toHaveCount(1);
  await expect(page.locator('img[alt^="notebook photo"]').first()).toBeVisible();

  // "What you wrote" reveals the raw transcript.
  const reveal = page.getByText("What you wrote");
  await expect(reveal).toBeVisible();
  await reveal.click();
  await expect(page.getByText("Voice note")).toBeVisible();
});

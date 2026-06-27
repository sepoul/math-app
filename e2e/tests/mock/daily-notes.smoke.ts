import { test, expect } from "@playwright/test";
import { mockPlatform } from "../../support/mock";
import { dailyNote } from "../../fixtures/artifacts";

test("history list renders note cards: date, preview, concepts, photo count", async ({ page }) => {
  const noteA = dailyNote({
    artifact_id: "note-a",
    note_date: "2026-06-20",
    image_refs: ["r1"],
    synthesis: {
      markdown: "## A\n\ntext",
      concepts: ["Group theory"],
      summary: "Cosets partition a group neatly.",
    },
  });
  const noteB = dailyNote({
    artifact_id: "note-b",
    note_date: "2026-06-19",
    image_refs: [],
    synthesis: {
      markdown: "## B\n\ntext",
      concepts: ["Calculus"],
      summary: "Reviewed the chain rule.",
    },
  });
  await mockPlatform(page, { notes: [noteA, noteB] });

  await page.goto("/math-notes");

  const cardA = page.locator('a[href="/math-notes/note-a"]');
  const cardB = page.locator('a[href="/math-notes/note-b"]');
  await expect(cardA).toBeVisible();
  await expect(cardB).toBeVisible();

  await expect(cardA).toContainText("2026-06-20");
  await expect(cardA).toContainText("Cosets partition a group neatly.");
  await expect(cardA).toContainText("Group theory"); // concept badge
  await expect(cardA).toContainText("1"); // photo count badge
  await expect(cardB).toContainText("Reviewed the chain rule.");
});

test("empty history shows the empty state", async ({ page }) => {
  await mockPlatform(page, { notes: [] });
  await page.goto("/math-notes");
  await expect(page.getByText(/No notes yet/i)).toBeVisible();
});

test('record page: "Don\'t spoil" flows through to the submit body', async ({ page }) => {
  const handle = await mockPlatform(page, { notes: [] });

  await page.goto("/math-notes/record");

  // Drive the file input (not the mic) so the smoke is deterministic.
  await page.setInputFiles('input[accept="audio/*"]', {
    name: "voice-note.m4a",
    mimeType: "audio/mp4",
    buffer: Buffer.from("fake-audio-bytes"),
  });

  // Toggle the "Don't spoil" directive on.
  const flair = page.getByRole("button", { name: "Don't spoil" });
  await flair.click();
  await expect(flair).toHaveAttribute("aria-pressed", "true");

  const save = page.getByRole("button", { name: /save note/i });
  await expect(save).toBeEnabled();
  await save.click();

  // The submit body carries the flair (and is the math_notes job).
  await expect.poll(() => handle.submissions.length).toBeGreaterThan(0);
  const body = handle.submissions[0];
  expect(body.job_type).toBe("math_notes");
  expect(body.flairs).toEqual(["dont_spoil"]);
  expect(body.audio_ref).toBeTruthy();
});

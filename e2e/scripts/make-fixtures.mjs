#!/usr/bin/env node
/**
 * Regenerate the `live` binary fixtures (committed, so running the suite needs
 * no extra tooling — only regenerating does):
 *
 *   fixtures/voice-note.m4a  — a short, clear math voice note (macOS `say`)
 *   fixtures/page-cosets.jpg — a photo-like image of hand-note math (PIL)
 *
 *   node scripts/make-fixtures.mjs      (or: npm run fixtures)
 *
 * macOS-only (uses `say` + `afconvert`); the image step needs python3 + Pillow.
 * Keep the clip short (<20s) and math-y so transcription + synthesis are quick.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "..", "fixtures");

const SPEECH =
  "Today I worked on cosets and Lagrange's theorem. " +
  "If H is a subgroup of a finite group G, then the left cosets of H partition G, " +
  "and every coset has the same number of elements as H. " +
  "Therefore the order of H divides the order of G, " +
  "and the index of H in G equals the order of G divided by the order of H.";

function makeAudio() {
  const tmp = mkdtempSync(join(tmpdir(), "e2e-fix-"));
  const aiff = join(tmp, "voice.aiff");
  try {
    execFileSync("say", ["-o", aiff, SPEECH], { stdio: "inherit" });
    execFileSync(
      "afconvert",
      ["-f", "m4af", "-d", "aac", aiff, join(FIX, "voice-note.m4a")],
      { stdio: "inherit" }
    );
    console.log("wrote fixtures/voice-note.m4a");
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

function makeImage() {
  const py = `
from PIL import Image, ImageDraw
img = Image.new("RGB", (900, 640), "white")
d = ImageDraw.Draw(img)
lines = [
    "Cosets of H in G",
    "",
    "g1 H, g2 H, ...  partition G",
    "each coset |gH| = |H|",
    "",
    "[G : H] = |G| / |H|",
    "so |H| divides |G|   (Lagrange)",
]
y = 60
for ln in lines:
    d.text((70, y), ln, fill="black")
    y += 70
img.save("${join(FIX, "page-cosets.jpg")}", "JPEG", quality=85)
print("wrote fixtures/page-cosets.jpg")
`;
  execFileSync("python3", ["-c", py], { stdio: "inherit" });
}

makeAudio();
makeImage();

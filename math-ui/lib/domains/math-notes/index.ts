/**
 * Math-notes domain — typed shapes + client for the `math_notes` ingest
 * job and `DailyNoteArtifact`. Built on top of `@/lib/platform`; the
 * platform never imports from this module.
 */
export type { DailyNoteArtifact, NotePage, NoteSynthesis, MediaRef } from "./types";
// Local mirror of the enriched (epic #14 / S5) synthesis shape — the SDK does
// not expose it yet (see synthesis-enriched.ts / TODO(#20)).
export type {
  DensityTier,
  NoteMagnitude,
  NoteSection,
  EnrichedNoteSynthesis,
} from "./synthesis-enriched";
export { notesClient, mediaSrc, mediaRefUrl } from "./client";
export { downscaleImage } from "./image";
export { NOTE_FLAIRS, type NoteFlairKey } from "./flairs";

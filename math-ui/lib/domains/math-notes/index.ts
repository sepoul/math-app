/**
 * Math-notes domain — typed shapes + client for the `math_notes` ingest
 * job and `DailyNoteArtifact`. Built on top of `@/lib/platform`; the
 * platform never imports from this module.
 */
export type { DailyNoteArtifact, NotePage, NoteSynthesis, MediaRef } from "./types";
export { notesClient, mediaSrc, mediaRefUrl } from "./client";
export { downscaleImage } from "./image";

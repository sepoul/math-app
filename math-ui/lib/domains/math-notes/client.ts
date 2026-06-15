import { jobsClient } from "@/lib/platform";
import type { RunSubmitResponse } from "@/lib/platform";
import type { MediaRef } from "./types";

/**
 * Math-notes domain client — the capture path is audio-first:
 *
 *   1. `uploadMedia(blob)` POSTs bytes to the BFF (`/api/media`),
 *      same-origin, proxied to the platform `POST /media`. Returns a
 *      `MediaRef` whose `storage_ref` you keep. Used for the voice note
 *      AND for each optional notebook photo.
 *   2. `ingestNote({ audioRef, imageRefs, … })` submits the `math_notes`
 *      job. The worker transcribes the audio (OpenAI) and mints the
 *      `DailyNoteArtifact{ transcript, image_refs, storage_ref=audio }`.
 *      Artifacts are only written by jobs — this is the write path.
 *
 * Upload goes through the BFF (not the platform directly) so the browser
 * stays same-origin over HTTPS.
 */
export const notesClient = {
  async uploadMedia(file: Blob, filename?: string): Promise<MediaRef> {
    const form = new FormData();
    const name = filename ?? (file instanceof File ? file.name : "upload");
    // Field name must be `file` — matches `POST /media`'s `UploadFile`.
    form.append("file", file, name);
    const res = await fetch("/api/media", { method: "POST", body: form });
    if (!res.ok) {
      throw new Error(`media upload failed (${res.status}): ${await res.text()}`);
    }
    return (await res.json()) as MediaRef;
  },

  ingestNote(input: {
    audioRef: string;
    imageRefs?: string[];
    noteDate?: string | null;
    createdBy?: string | null;
  }): Promise<RunSubmitResponse> {
    return jobsClient.submit({
      job_type: "math_notes",
      audio_ref: input.audioRef,
      image_refs: input.imageRefs ?? [],
      note_date: input.noteDate ?? null,
      created_by: input.createdBy ?? null,
    });
  },
};

/**
 * A hydrated artifact `storage_url` (`/media/download?ref=…`, filled in by
 * `GET /artifacts/{id}`) → same-origin URL the browser loads via the BFF.
 */
export function mediaSrc(storageUrl: string): string {
  return storageUrl.startsWith("/api") ? storageUrl : `/api${storageUrl}`;
}

/**
 * A raw `storage_ref` (e.g. one of a note's `image_refs`, which aren't
 * hydrated into URLs) → the same-origin download URL through the BFF.
 */
export function mediaRefUrl(ref: string): string {
  return `/api/media/download?ref=${encodeURIComponent(ref)}`;
}

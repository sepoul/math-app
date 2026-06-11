import { jobsClient } from "@/lib/platform";
import type { RunSubmitResponse } from "@/lib/platform";
import type { MediaRef } from "./types";

/**
 * Math-notes domain client — the two-step capture path:
 *
 *   1. `uploadMedia(file)` POSTs the bytes to the BFF (`/api/media`),
 *      same-origin, which proxies to the platform `POST /media`. Returns
 *      a `storage_ref`.
 *   2. `ingestNote({ storageRef, … })` submits the `math_notes` job with
 *      that ref; the job mints the `DailyNoteArtifact` (artifacts are
 *      only written by jobs — there's no `POST /artifacts`).
 *
 * Upload goes through the BFF rather than the platform directly so the
 * browser stays same-origin over HTTPS (no mixed-content; the API URL
 * never leaves the server).
 */
export const notesClient = {
  async uploadMedia(file: File): Promise<MediaRef> {
    const form = new FormData();
    // Field name must be `file` — matches `POST /media`'s `UploadFile`.
    form.append("file", file);
    const res = await fetch("/api/media", { method: "POST", body: form });
    if (!res.ok) {
      throw new Error(`media upload failed (${res.status}): ${await res.text()}`);
    }
    return (await res.json()) as MediaRef;
  },

  ingestNote(input: {
    storageRef: string;
    contentType?: string | null;
    byteSize?: number | null;
    noteDate?: string | null;
    createdBy?: string | null;
  }): Promise<RunSubmitResponse> {
    return jobsClient.submit({
      job_type: "math_notes",
      storage_ref: input.storageRef,
      content_type: input.contentType ?? null,
      byte_size: input.byteSize ?? null,
      note_date: input.noteDate ?? null,
      created_by: input.createdBy ?? null,
    });
  },
};

/**
 * Turn a platform-relative `storage_url` (`/media/download?ref=…`, as
 * hydrated onto an artifact by `GET /artifacts/{id}`) into a same-origin
 * URL the browser can load through the BFF.
 */
export function mediaSrc(storageUrl: string): string {
  return storageUrl.startsWith("/api") ? storageUrl : `/api${storageUrl}`;
}

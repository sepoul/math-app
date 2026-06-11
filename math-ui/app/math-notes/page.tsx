"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Loader2, RefreshCw } from "lucide-react";
import { PageContainer, PageHeader, Section, EmptyCard, ErrorCard } from "@/components/library";
import {
  fetchArtifacts,
  fetchArtifact,
  jobsClient,
  TERMINAL_JOB_STATUSES,
} from "@/lib/platform";
import { notesClient, mediaSrc, type DailyNoteArtifact } from "@/lib/domains/math-notes";

// Single-learner MVP — `created_by` is stamped but not yet filtered on
// (server-side `created_by` filtering is PR-3, not built). Per-user
// scoping arrives with auth.
const LEARNER = "me";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Poll a just-submitted job until it leaves the running states. Ingest
 * is near-instant (no LLM), so a short poll is enough. */
async function waitForJob(jobId: string): Promise<void> {
  for (let i = 0; i < 30; i++) {
    const status = await jobsClient.getStatus(jobId);
    if ((TERMINAL_JOB_STATUSES as readonly string[]).includes(status.status)) return;
    await new Promise((r) => setTimeout(r, 500));
  }
}

export default function MathNotesPage() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [noteDate, setNoteDate] = useState<string>(todayISO());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [notes, setNotes] = useState<DailyNoteArtifact[]>([]);
  const [notesError, setNotesError] = useState<string | null>(null);
  const [loadingNotes, setLoadingNotes] = useState(true);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadNotes = useCallback(async () => {
    setLoadingNotes(true);
    setNotesError(null);
    try {
      const list = await fetchArtifacts({ artifactType: "daily_note", limit: 100 });
      const summaries = list.artifacts.filter((a) => a.artifact_type === "daily_note");
      // The list endpoint returns summaries (no storage_url); fetch each
      // by id to get the hydrated download URL + note metadata.
      const full = await Promise.all(
        summaries.map((s) => fetchArtifact(s.artifact_id) as Promise<DailyNoteArtifact>)
      );
      full.sort((a, b) => (a.note_date < b.note_date ? 1 : -1));
      setNotes(full);
    } catch (e) {
      setNotesError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingNotes(false);
    }
  }, []);

  useEffect(() => {
    void loadNotes();
  }, [loadNotes]);

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    setFile(picked);
    setError(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(picked ? URL.createObjectURL(picked) : null);
  }

  async function onSave() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setStatus("Uploading photo…");
      const ref = await notesClient.uploadMedia(file);
      setStatus("Saving note…");
      const sub = await notesClient.ingestNote({
        storageRef: ref.storage_ref,
        contentType: ref.content_type,
        byteSize: ref.byte_size,
        noteDate,
        createdBy: LEARNER,
      });
      await waitForJob(sub.job_id);
      // Clear the form and refresh the gallery.
      setFile(null);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
      if (fileInput.current) fileInput.current.value = "";
      setStatus(null);
      await loadNotes();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Daily notes"
        subtitle="Snap a photo of today's notebook page and save it as a dated note."
      />

      <Section title="Capture">
        <div className="max-w-md space-y-4">
          <label
            htmlFor="note-photo"
            className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/30 px-4 py-8 text-sm text-muted-foreground transition-colors hover:bg-muted/50"
          >
            <Camera className="size-6" />
            {file ? file.name : "Tap to take a photo (or choose one)"}
            <input
              id="note-photo"
              ref={fileInput}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={onPick}
            />
          </label>

          {previewUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={previewUrl}
              alt="Selected note preview"
              className="max-h-72 w-full rounded-md border object-contain"
            />
          )}

          <div className="flex items-center gap-3">
            <label htmlFor="note-date" className="text-sm font-medium">
              Date
            </label>
            <input
              id="note-date"
              type="date"
              value={noteDate}
              max={todayISO()}
              onChange={(e) => setNoteDate(e.target.value)}
              className="rounded-md border bg-background px-2.5 py-1.5 text-sm"
            />
          </div>

          <button
            type="button"
            onClick={onSave}
            disabled={!file || busy}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {busy && <Loader2 className="size-4 animate-spin" />}
            {busy ? (status ?? "Saving…") : "Save note"}
          </button>

          {error && <ErrorCard>{error}</ErrorCard>}
        </div>
      </Section>

      <Section
        title="Your notes"
        actions={
          <button
            type="button"
            onClick={() => void loadNotes()}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className="size-3.5" />
            Refresh
          </button>
        }
      >
        {notesError ? (
          <ErrorCard>{notesError}</ErrorCard>
        ) : loadingNotes ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : notes.length === 0 ? (
          <EmptyCard>No notes yet. Capture your first one above.</EmptyCard>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {notes.map((note) => (
              <figure key={note.artifact_id} className="space-y-1.5">
                {note.storage_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={mediaSrc(note.storage_url)}
                    alt={`Note from ${note.note_date}`}
                    className="aspect-[3/4] w-full rounded-md border object-cover"
                  />
                ) : (
                  <div className="flex aspect-[3/4] w-full items-center justify-center rounded-md border bg-muted text-xs text-muted-foreground">
                    no image
                  </div>
                )}
                <figcaption className="text-xs text-muted-foreground">{note.note_date}</figcaption>
              </figure>
            ))}
          </div>
        )}
      </Section>
    </PageContainer>
  );
}

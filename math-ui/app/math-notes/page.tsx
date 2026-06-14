"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, ImagePlus, Loader2, Mic, RefreshCw, Square, X } from "lucide-react";
import { PageContainer, PageHeader, Section, EmptyCard, ErrorCard } from "@/components/library";
import { Button } from "@/components/ui/button";
import {
  fetchArtifacts,
  fetchArtifact,
  jobsClient,
  TERMINAL_JOB_STATUSES,
} from "@/lib/platform";
import {
  notesClient,
  mediaSrc,
  mediaRefUrl,
  type DailyNoteArtifact,
} from "@/lib/domains/math-notes";

// Single-learner MVP — `created_by` is stamped but not yet filtered on
// (server-side filtering is PR-3). Per-user scoping arrives with auth.
const LEARNER = "me";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function audioExt(mime: string): string {
  if (mime.includes("mp4") || mime.includes("m4a") || mime.includes("aac")) return "m4a";
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("wav")) return "wav";
  if (mime.includes("mpeg") || mime.includes("mp3")) return "mp3";
  return "webm";
}

/** Poll a just-submitted job until it leaves the running states. The
 * worker transcribes the audio (one OpenAI call), so a short poll covers it. */
async function waitForJob(jobId: string): Promise<string> {
  for (let i = 0; i < 60; i++) {
    const s = await jobsClient.getStatus(jobId);
    if ((TERMINAL_JOB_STATUSES as readonly string[]).includes(s.status)) return s.status;
    await new Promise((r) => setTimeout(r, 500));
  }
  return "TIMEOUT";
}

export default function MathNotesPage() {
  // --- voice note ---
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  // Gate client-only capabilities behind `mounted` so the server render and
  // the first client render agree (both treat recording as unavailable);
  // otherwise the Record button's presence differs → hydration mismatch.
  const [mounted, setMounted] = useState(false);
  const canRecord = mounted && typeof window.MediaRecorder !== "undefined";

  // --- photos ---
  const [photos, setPhotos] = useState<File[]>([]);
  const [photoUrls, setPhotoUrls] = useState<string[]>([]);

  // --- form / submit ---
  const [noteDate, setNoteDate] = useState(todayISO());
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- gallery ---
  const [notes, setNotes] = useState<DailyNoteArtifact[]>([]);
  const [loadingNotes, setLoadingNotes] = useState(true);
  const [notesError, setNotesError] = useState<string | null>(null);

  const setAudio = useCallback(
    (blob: Blob | null) => {
      setAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return blob ? URL.createObjectURL(blob) : null;
      });
      setAudioBlob(blob);
    },
    []
  );

  const loadNotes = useCallback(async () => {
    setLoadingNotes(true);
    setNotesError(null);
    try {
      const list = await fetchArtifacts({ artifactType: "daily_note", limit: 100 });
      const summaries = list.artifacts.filter((a) => a.artifact_type === "daily_note");
      // List endpoint returns summaries (no storage_url/transcript); fetch
      // each by id for the hydrated audio URL + transcript + image refs.
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
    setMounted(true);
  }, []);

  useEffect(() => {
    void loadNotes();
  }, [loadNotes]);

  // ---- recording ----
  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const type = rec.mimeType || "audio/webm";
        setAudio(new Blob(chunksRef.current, { type }));
        stream.getTracks().forEach((t) => t.stop());
      };
      recorderRef.current = rec;
      rec.start();
      setRecording(true);
    } catch (e) {
      setError(`microphone unavailable: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  function onPickAudio(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setAudio(f);
  }

  function onPickPhotos(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    // Append, so "Take photo" and "Add from library" (and repeat taps)
    // accumulate instead of replacing.
    setPhotos((prev) => [...prev, ...files]);
    setPhotoUrls((prev) => [...prev, ...files.map((f) => URL.createObjectURL(f))]);
    // Reset so the same file — or another camera shot — can be picked again.
    e.target.value = "";
  }

  function removePhoto(i: number) {
    URL.revokeObjectURL(photoUrls[i]);
    setPhotos((p) => p.filter((_, idx) => idx !== i));
    setPhotoUrls((u) => u.filter((_, idx) => idx !== i));
  }

  async function onSave() {
    if (!audioBlob) {
      setError("Record or choose a voice note first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setStatus("Uploading voice note…");
      const audio = await notesClient.uploadMedia(
        audioBlob,
        `voice-note.${audioExt(audioBlob.type)}`
      );

      const imageRefs: string[] = [];
      for (let i = 0; i < photos.length; i++) {
        setStatus(`Uploading photo ${i + 1}/${photos.length}…`);
        const ref = await notesClient.uploadMedia(photos[i]);
        imageRefs.push(ref.storage_ref);
      }

      setStatus("Transcribing + saving…");
      const sub = await notesClient.ingestNote({
        audioRef: audio.storage_ref,
        imageRefs,
        noteDate,
        createdBy: LEARNER,
      });
      const final = await waitForJob(sub.job_id);
      if (final === "FAILED") throw new Error("Ingest job failed — check worker logs.");

      // reset form
      setAudio(null);
      photoUrls.forEach((u) => URL.revokeObjectURL(u));
      setPhotos([]);
      setPhotoUrls([]);
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
        subtitle="Record a short voice note about today's session (and optionally snap your notebook). It gets transcribed and saved as a dated note."
      />

      <Section title="Capture">
        <div className="max-w-md space-y-5">
          {/* voice note */}
          <div className="space-y-2">
            <p className="text-sm font-medium">Voice note</p>
            <div className="flex flex-wrap items-center gap-3">
              {canRecord &&
                (recording ? (
                  <Button variant="destructive" onClick={stopRecording}>
                    <Square /> Stop
                  </Button>
                ) : (
                  <Button variant="tonal" onClick={startRecording} disabled={busy}>
                    <Mic /> {audioBlob ? "Re-record" : "Record"}
                  </Button>
                ))}
              <label className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
                or choose a file
                <input
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={onPickAudio}
                />
              </label>
            </div>
            {recording && (
              <p className="flex items-center gap-1.5 text-xs text-red-600">
                <span className="size-2 animate-pulse rounded-full bg-red-600" /> recording…
              </p>
            )}
            {audioUrl && !recording && (
              <audio controls src={audioUrl} className="w-full" />
            )}
          </div>

          {/* photos */}
          <div className="space-y-2">
            <p className="text-sm font-medium">
              Notebook photos <span className="text-muted-foreground">(optional)</span>
            </p>
            <div className="flex flex-wrap gap-2">
              {/* Direct rear-camera capture on phones (capture="environment",
                  single shot — repeatable). */}
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground">
                <Camera className="size-4" /> Take photo
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  className="hidden"
                  onChange={onPickPhotos}
                />
              </label>
              {/* Library / multi-select (no `capture`, so the OS offers the
                  photo library and honours `multiple`). */}
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground">
                <ImagePlus className="size-4" /> Add from library
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={onPickPhotos}
                />
              </label>
            </div>
            {photoUrls.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {photoUrls.map((u, i) => (
                  <div key={u} className="relative">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={u} alt={`photo ${i + 1}`} className="size-20 rounded-md border object-cover" />
                    <button
                      type="button"
                      onClick={() => removePhoto(i)}
                      className="absolute -right-1.5 -top-1.5 rounded-full bg-foreground p-0.5 text-background"
                      aria-label="remove photo"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* date + save */}
          <div className="flex items-center gap-3">
            <label htmlFor="note-date" className="text-sm font-medium">Date</label>
            <input
              id="note-date"
              type="date"
              value={noteDate}
              max={todayISO()}
              onChange={(e) => setNoteDate(e.target.value)}
              className="rounded-md border bg-background px-2.5 py-1.5 text-sm"
            />
          </div>

          <Button onClick={onSave} disabled={!audioBlob || busy || recording}>
            {busy && <Loader2 className="animate-spin" />}
            {busy ? (status ?? "Saving…") : "Save note"}
          </Button>

          {error && <ErrorCard>{error}</ErrorCard>}
        </div>
      </Section>

      <Section
        title="Your notes"
        actions={
          <Button variant="ghost" size="sm" onClick={() => void loadNotes()}>
            <RefreshCw /> Refresh
          </Button>
        }
      >
        {notesError ? (
          <ErrorCard>{notesError}</ErrorCard>
        ) : loadingNotes ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : notes.length === 0 ? (
          <EmptyCard>No notes yet. Record your first one above.</EmptyCard>
        ) : (
          <ul className="space-y-4">
            {notes.map((note) => (
              <li key={note.artifact_id} className="space-y-2 rounded-2xl border border-border bg-card p-4 shadow-e1">
                <div className="text-xs font-medium text-muted-foreground">{note.note_date}</div>
                {note.storage_url && (
                  <audio controls src={mediaSrc(note.storage_url)} className="w-full" />
                )}
                <p className="text-sm">
                  {note.transcript ?? <span className="text-muted-foreground italic">no transcript</span>}
                </p>
                {note.image_refs && note.image_refs.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {note.image_refs.map((ref) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={ref}
                        src={mediaRefUrl(ref)}
                        alt="notebook photo"
                        className="size-24 rounded-md border object-cover"
                      />
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </PageContainer>
  );
}

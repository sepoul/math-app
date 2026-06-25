"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Camera, ImagePlus, Loader2, Mic, Square, X } from "lucide-react";
import { PageContainer, PageHeader, Section, ErrorCard } from "@/components/library";
import { Button, buttonVariants } from "@/components/ui/button";
import { jobsClient, TERMINAL_JOB_STATUSES } from "@/lib/platform";
import { notesClient, downscaleImage, NOTE_FLAIRS } from "@/lib/domains/math-notes";

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

/** Poll a just-submitted job until it leaves the running states. The worker
 * transcribes the audio, extracts the photos, and runs one synthesis pass, so
 * a short poll covers it. */
async function waitForJob(jobId: string): Promise<string> {
  for (let i = 0; i < 120; i++) {
    const s = await jobsClient.getStatus(jobId);
    if ((TERMINAL_JOB_STATUSES as readonly string[]).includes(s.status)) return s.status;
    await new Promise((r) => setTimeout(r, 500));
  }
  return "TIMEOUT";
}

export default function RecordNotePage() {
  const router = useRouter();

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

  // --- flairs: learner directives that steer the synthesis (default none) ---
  const [flairs, setFlairs] = useState<string[]>([]);
  function toggleFlair(key: string) {
    setFlairs((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  const setAudio = useCallback((blob: Blob | null) => {
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return blob ? URL.createObjectURL(blob) : null;
    });
    setAudioBlob(blob);
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

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

  async function onPickPhotos(e: React.ChangeEvent<HTMLInputElement>) {
    const input = e.target;
    const files = Array.from(input.files ?? []);
    // Reset now (before any await, while the target is current) so the same
    // file — or another camera shot — can be picked again.
    input.value = "";
    if (files.length === 0) return;
    // Downscale on selection so the multi-MB originals are shrunk to a few
    // hundred KB before they're ever uploaded, and previews use the small
    // version too. downscaleImage never throws (returns the original on any
    // failure), so capture is never blocked.
    const shrunk = await Promise.all(files.map((f) => downscaleImage(f)));
    // Append, so "Take photo" and "Add from library" (and repeat taps)
    // accumulate instead of replacing.
    setPhotos((prev) => [...prev, ...shrunk]);
    setPhotoUrls((prev) => [...prev, ...shrunk.map((f) => URL.createObjectURL(f))]);
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

      setStatus("Transcribing + synthesising…");
      const sub = await notesClient.ingestNote({
        audioRef: audio.storage_ref,
        imageRefs,
        noteDate,
        createdBy: LEARNER,
        flairs,
      });
      const final = await waitForJob(sub.job_id);
      if (final === "FAILED") throw new Error("Ingest job failed — check worker logs.");

      // Release previews and hand back to the history list.
      setAudio(null);
      photoUrls.forEach((u) => URL.revokeObjectURL(u));
      setPhotos([]);
      setPhotoUrls([]);
      setFlairs([]);
      setStatus(null);
      toast.success("Note saved.");
      router.push("/math-notes");
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
        title="New note"
        subtitle="Record a short voice note about today's session (and optionally snap your notebook). It gets transcribed and synthesised into a clean, dated note."
        actions={
          <Link
            href="/math-notes"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            <ArrowLeft /> Back
          </Link>
        }
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

          {/* flairs — learner directives that steer the synthesis */}
          <div className="space-y-2">
            <p className="text-sm font-medium">
              Directives <span className="text-muted-foreground">(optional)</span>
            </p>
            <div className="flex flex-wrap gap-2">
              {NOTE_FLAIRS.map((f) => {
                const on = flairs.includes(f.key);
                return (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => toggleFlair(f.key)}
                    aria-pressed={on}
                    title={f.description}
                    className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors ${
                      on
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border hover:bg-accent hover:text-accent-foreground"
                    }`}
                  >
                    {f.label}
                  </button>
                );
              })}
            </div>
            {flairs.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {NOTE_FLAIRS.filter((f) => flairs.includes(f.key))
                  .map((f) => f.description)
                  .join(" ")}
              </p>
            )}
          </div>

          <Button onClick={onSave} disabled={!audioBlob || busy || recording}>
            {busy && <Loader2 className="animate-spin" />}
            {busy ? (status ?? "Saving…") : "Save note"}
          </Button>

          {error && <ErrorCard>{error}</ErrorCard>}
        </div>
      </Section>
    </PageContainer>
  );
}

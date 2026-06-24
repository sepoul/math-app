"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Image as ImageIcon, Mic, Plus, RefreshCw } from "lucide-react";
import {
  PageContainer,
  PageHeader,
  Section,
  EmptyCard,
  ErrorCard,
  LinkCard,
} from "@/components/library";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { fetchArtifactsFull } from "@/lib/platform";
import { type DailyNoteArtifact } from "@/lib/domains/math-notes";

export default function MathNotesPage() {
  const [notes, setNotes] = useState<DailyNoteArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadNotes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // One request returns the full self-contained notes — pages (raw
      // extraction) and synthesis are embedded on each daily_note, so there's
      // no per-note `note_page` N+1 to follow.
      const resp = await fetchArtifactsFull({ artifactType: "daily_note", limit: 100 });
      const full = resp.artifacts as unknown as DailyNoteArtifact[];
      full.sort((a, b) => (a.note_date < b.note_date ? 1 : -1));
      setNotes(full);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadNotes();
  }, [loadNotes]);

  return (
    <PageContainer>
      <PageHeader
        title="Daily notes"
        subtitle="Your captured study sessions. Each note is transcribed and synthesised into clean, coherent math, saved by date."
        actions={
          <Link
            href="/math-notes/record"
            className={buttonVariants({ variant: "default", size: "sm" })}
          >
            <Plus /> New note
          </Link>
        }
      />

      <Section
        title="Your notes"
        actions={
          <Button variant="ghost" size="sm" onClick={() => void loadNotes()}>
            <RefreshCw /> Refresh
          </Button>
        }
      >
        {error ? (
          <ErrorCard>{error}</ErrorCard>
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : notes.length === 0 ? (
          <EmptyCard>
            No notes yet.{" "}
            <Link className="underline" href="/math-notes/record">
              Record your first one.
            </Link>
          </EmptyCard>
        ) : (
          <ul className="space-y-3">
            {notes.map((note) => {
              const concepts = note.synthesis?.concepts ?? [];
              const preview =
                note.synthesis?.summary ?? note.transcript ?? "No transcript";
              const photoCount = note.image_refs?.length ?? 0;
              return (
                <li key={note.artifact_id}>
                  <LinkCard href={`/math-notes/${note.artifact_id}`}>
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground">
                        <span>{note.note_date}</span>
                        {note.storage_url && <Mic className="size-3.5" />}
                        {photoCount > 0 && (
                          <span className="inline-flex items-center gap-1">
                            <ImageIcon className="size-3.5" /> {photoCount}
                          </span>
                        )}
                      </div>
                      <p className="line-clamp-2 text-sm text-foreground">{preview}</p>
                      {concepts.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {concepts.slice(0, 4).map((c) => (
                            <Badge key={c} variant="secondary">{c}</Badge>
                          ))}
                          {concepts.length > 4 && (
                            <Badge variant="outline">+{concepts.length - 4}</Badge>
                          )}
                        </div>
                      )}
                    </div>
                  </LinkCard>
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    </PageContainer>
  );
}

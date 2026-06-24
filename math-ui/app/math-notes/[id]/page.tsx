"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { fetchArtifact } from "@/lib/platform";
import {
  ErrorCard,
  LoadingCard,
  PageContainer,
  PageHeader,
} from "@/components/library";
import { buttonVariants } from "@/components/ui/button";
import { NoteView } from "@/components/notes/note-view";
import type { DailyNoteArtifact } from "@/lib/domains/math-notes";

interface Props {
  params: Promise<{ id: string }>;
}

export default function NoteDetailPage({ params }: Props) {
  const { id } = use(params);
  const [note, setNote] = useState<DailyNoteArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchArtifact(id)
      .then((a) => {
        if (cancelled) return;
        if (a.artifact_type !== "daily_note") {
          setError(`Artifact ${id} is a ${a.artifact_type}, not a daily note.`);
          return;
        }
        setNote(a as unknown as DailyNoteArtifact);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <PageContainer>
      <PageHeader
        title={note ? `Note · ${note.note_date}` : "Note"}
        subtitle={<span className="font-mono text-xs">{id}</span>}
        actions={
          <Link
            href="/math-notes"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            <ArrowLeft /> Back
          </Link>
        }
      />

      {error && <ErrorCard>{error}</ErrorCard>}
      {!error && !note && <LoadingCard rows={5} />}
      {note && (
        <div className="max-w-2xl rounded-2xl border border-border bg-card p-5 shadow-e1">
          <NoteView note={note} />
        </div>
      )}
    </PageContainer>
  );
}

import { Badge } from "@/components/ui/badge";
import { Latex } from "@/components/library";
import { mediaSrc, mediaRefUrl, type DailyNoteArtifact } from "@/lib/domains/math-notes";

/**
 * Full render of one daily note under the unified document schema. The
 * note-level `synthesis` (a coherent markdown document with embedded
 * KaTeX-validated math) is the primary view; the raw material it was built
 * from — the voice-note transcript + each photo's faithful transcription —
 * stays available in a collapsible "What you wrote".
 *
 * Old rows (pre-redesign, `schema_version` 1) have no `synthesis` and no
 * embedded `pages`; they fall back to showing the transcript directly, so a
 * note never renders empty before the migration runs.
 */
export function NoteView({ note }: { note: DailyNoteArtifact }) {
  const synthesis = note.synthesis ?? null;
  const hasSynthesis = Boolean(synthesis?.markdown);
  const rawPages = (note.pages ?? []).filter(
    (p) => p.raw_text || p.diagram_description
  );
  // Reveal the raw material only when the synthesis is the primary view —
  // without a synthesis the transcript is already shown in full above.
  const showRaw =
    hasSynthesis && (Boolean(note.transcript) || rawPages.length > 0);

  return (
    <div className="space-y-4">
      {synthesis?.summary && (
        <p className="text-sm text-muted-foreground">{synthesis.summary}</p>
      )}

      {hasSynthesis ? (
        <Latex className="text-sm">{synthesis!.markdown!}</Latex>
      ) : note.transcript ? (
        <p className="whitespace-pre-wrap text-sm">{note.transcript}</p>
      ) : (
        <p className="text-sm italic text-muted-foreground">No synthesis yet.</p>
      )}

      {synthesis?.concepts && synthesis.concepts.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {synthesis.concepts.map((c) => (
            <Badge key={c} variant="secondary">{c}</Badge>
          ))}
        </div>
      )}

      {note.storage_url && (
        <audio controls src={mediaSrc(note.storage_url)} className="w-full" />
      )}

      {note.image_refs && note.image_refs.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-1">
          {note.image_refs.map((ref) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={ref}
              src={mediaRefUrl(ref)}
              alt="notebook photo"
              className="size-28 rounded-md border object-cover"
            />
          ))}
        </div>
      )}

      {showRaw && (
        <details className="rounded-xl border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
          <summary className="cursor-pointer select-none font-medium">
            What you wrote
          </summary>
          <div className="mt-2 space-y-3">
            {note.transcript && (
              <div>
                <div className="text-xs font-medium">Voice note</div>
                <p className="mt-1 whitespace-pre-wrap">{note.transcript}</p>
              </div>
            )}
            {rawPages.map((page) => (
              <div key={page.page_index}>
                <div className="text-xs font-medium">Page {page.page_index + 1}</div>
                {page.raw_text && (
                  <p className="mt-1 whitespace-pre-wrap">{page.raw_text}</p>
                )}
                {page.diagram_description && (
                  <p className="mt-1 italic">Diagram: {page.diagram_description}</p>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

import { Badge } from "@/components/ui/badge";
import { MarkdownMath } from "@/components/library";
import {
  mediaSrc,
  type DailyNoteArtifact,
  type EnrichedNoteSynthesis,
  type NoteMagnitude,
} from "@/lib/domains/math-notes";
import { NotePhotos } from "./note-photos";
import { MagnitudeBadge } from "./note-magnitude-badge";

/**
 * Full render of one daily note under the unified document schema. The
 * note-level `synthesis` is the primary view; the raw material it was built
 * from — the voice-note transcript + each photo's faithful transcription —
 * stays available in a collapsible "What you wrote".
 *
 * The synthesis renders at one of three fidelities, picked by what's present
 * (epic #14, S6):
 *   1. **Sectioned** (`synthesis.sections`): a substantial, multi-topic
 *      session renders one navigable `<section>` per topic — heading +
 *      KaTeX-validated Markdown + per-section concept chips — with a small
 *      "Topics" nav and a depth/magnitude badge.
 *   2. **Flat** (`synthesis.markdown`): a short, single-topic note renders the
 *      one Markdown blob, exactly as before the enrichment (no regression).
 *   3. **Raw** (old `schema_version` 1 rows with no synthesis): falls back to
 *      the transcript, so a note never renders empty before the migration runs.
 */
export function NoteView({ note }: { note: DailyNoteArtifact }) {
  // The enriched (epic #14 / S5) synthesis fields — `sections`, `depth_tier`,
  // embedded `magnitude` — and the top-level `magnitude` are not in the SDK
  // types yet, so read them through the local mirror.
  // TODO(#20): drop these casts once the SDK is regenerated (see types.ts).
  const synthesis = (note.synthesis ?? null) as EnrichedNoteSynthesis | null;
  const magnitude: NoteMagnitude | null =
    synthesis?.magnitude ??
    (note as { magnitude?: NoteMagnitude | null }).magnitude ??
    null;

  const sections = (synthesis?.sections ?? []).filter(
    (s) => s.markdown || s.heading
  );
  const hasSections = sections.length > 0;
  const hasFlatMarkdown = Boolean(synthesis?.markdown);

  const rawPages = (note.pages ?? []).filter(
    (p) => p.raw_text || p.diagram_description
  );
  // Reveal the raw material only when a synthesis is the primary view —
  // without one the transcript is already shown in full above.
  const showRaw =
    (hasSections || hasFlatMarkdown) &&
    (Boolean(note.transcript) || rawPages.length > 0);

  return (
    <div className="space-y-4">
      <MagnitudeBadge synthesis={synthesis} magnitude={magnitude} />

      {synthesis?.summary && (
        <p className="text-sm text-muted-foreground">{synthesis.summary}</p>
      )}

      {hasSections ? (
        <div className="space-y-5">
          {sections.length > 1 && (
            <nav
              aria-label="Sections"
              className="rounded-xl border border-border bg-muted/30 p-3"
            >
              <div className="text-xs font-medium text-muted-foreground">
                Topics
              </div>
              <ol className="mt-1.5 space-y-1 text-sm">
                {sections.map((s, i) => (
                  <li key={sectionAnchor(i)}>
                    <a
                      href={`#${sectionAnchor(i)}`}
                      className="text-primary underline decoration-primary/30 underline-offset-2 hover:decoration-primary"
                    >
                      {s.heading || `Section ${i + 1}`}
                    </a>
                  </li>
                ))}
              </ol>
            </nav>
          )}

          {sections.map((s, i) => (
            <section
              key={sectionAnchor(i)}
              id={sectionAnchor(i)}
              className="scroll-mt-4 space-y-2"
            >
              {s.heading && (
                <h2 className="text-sm font-semibold tracking-tight">
                  {s.heading}
                </h2>
              )}
              {s.markdown && (
                <MarkdownMath className="text-sm">{s.markdown}</MarkdownMath>
              )}
              {s.concepts && s.concepts.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {s.concepts.map((c) => (
                    <Badge key={c} variant="secondary">
                      {c}
                    </Badge>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      ) : hasFlatMarkdown ? (
        <MarkdownMath className="text-sm">{synthesis!.markdown!}</MarkdownMath>
      ) : note.transcript ? (
        <p className="whitespace-pre-wrap text-sm">{note.transcript}</p>
      ) : (
        <p className="text-sm italic text-muted-foreground">No synthesis yet.</p>
      )}

      {/* Note-level concepts for a flat note. Sectioned notes carry their
          concepts per-section above, so we don't repeat them here. */}
      {!hasSections && synthesis?.concepts && synthesis.concepts.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {synthesis.concepts.map((c) => (
            <Badge key={c} variant="secondary">
              {c}
            </Badge>
          ))}
        </div>
      )}

      {note.storage_url && (
        <audio controls src={mediaSrc(note.storage_url)} className="w-full" />
      )}

      {note.image_refs && note.image_refs.length > 0 && (
        <NotePhotos refs={note.image_refs} />
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

/** Stable anchor id for a section's nav link + scroll target. */
function sectionAnchor(index: number): string {
  return `note-section-${index + 1}`;
}

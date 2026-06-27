/**
 * Mock fixtures for the `mock` project. These mirror the platform's
 * `DailyNoteArtifact` JSON shape (see `math-ui/lib/domains/math-notes/types.ts`
 * → `@sepoul-packages/sdk` schema) closely enough to drive the UI; they are
 * deliberately hand-rolled (not imported from the SDK) so `e2e/` stays a
 * standalone package with zero math-ui/platform deps.
 */

/** Loose mirror of the platform `DailyNoteArtifact` (only the fields the UI reads). */
export interface DailyNoteFixture {
  artifact_id: string;
  artifact_type: "daily_note";
  created_at: string;
  created_by_job?: string | null;
  storage_ref?: string | null;
  storage_url?: string | null;
  note_date: string;
  created_by?: string | null;
  image_refs?: string[];
  transcript?: string | null;
  pages?: Array<{
    page_index: number;
    image_ref: string;
    raw_text?: string | null;
    diagram_description?: string | null;
  }>;
  synthesis?: {
    markdown?: string | null;
    concepts?: string[];
    summary?: string | null;
    model_used?: string | null;
    validation_attempts?: number;
  } | null;
  schema_version: number;
}

/**
 * The synthesis markdown that the rendering smoke guards: a real `## heading`,
 * `**bold**`, a `-` list, `$inline$` math, and a `$$display$$` block. If
 * `MarkdownMath` ever regresses to dumping the raw string, the literal
 * `##` / `**` / `$$` delimiters leak into the visible text and the smoke fails.
 */
export const RICH_MARKDOWN = `## Cosets and Lagrange's theorem

A subgroup $H \\le G$ partitions $G$ into **left cosets** $gH$. The key facts:

- Every coset $gH$ has the same size as $H$.
- Two cosets are either **equal or disjoint**.

So the order of $H$ divides the order of $G$:

$$
[G : H] = \\frac{|G|}{|H|}
$$
`;

let seq = 0;

/** Build a `daily_note` fixture; override any field. */
export function dailyNote(
  overrides: Partial<DailyNoteFixture> = {}
): DailyNoteFixture {
  seq += 1;
  const id = overrides.artifact_id ?? `note-${seq}`;
  return {
    artifact_id: id,
    artifact_type: "daily_note",
    created_at: "2026-06-20T09:00:00Z",
    created_by_job: `job-${seq}`,
    note_date: "2026-06-20",
    created_by: "me",
    storage_ref: `audio-ref-${seq}`,
    // `storage_url` is hydrated by GET /artifacts/{id}; the UI builds the
    // <audio> src from it via mediaSrc() → /api/media/download?...
    storage_url: `/media/download?ref=audio-ref-${seq}`,
    image_refs: [],
    transcript: "Today I reviewed cosets and proved Lagrange's theorem.",
    pages: [],
    synthesis: {
      markdown: RICH_MARKDOWN,
      concepts: ["Group theory", "Cosets", "Lagrange's theorem"],
      summary: "Cosets partition a group; their common size proves Lagrange.",
      model_used: "claude-opus-mock",
      validation_attempts: 1,
    },
    schema_version: 2,
    ...overrides,
  };
}

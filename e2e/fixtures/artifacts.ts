/**
 * Mock fixtures for the `mock` project. These mirror the platform's
 * `DailyNoteArtifact` JSON shape (see `math-ui/lib/domains/math-notes/types.ts`
 * → `@sepoul-packages/sdk` schema) closely enough to drive the UI; they are
 * deliberately hand-rolled (not imported from the SDK) so `e2e/` stays a
 * standalone package with zero math-ui/platform deps.
 */

type DensityTier = "brief" | "standard" | "deep";

/** Loose mirror of the platform `NoteMagnitude` (enriched synthesis, epic #14). */
export interface NoteMagnitudeFixture {
  transcript_chars: number;
  page_count: number;
  page_chars: number;
  density_tier: DensityTier;
  duration_seconds?: number | null;
}

/** Loose mirror of the platform `NoteSection` (one topical section). */
export interface NoteSectionFixture {
  heading: string;
  markdown: string;
  concepts: string[];
}

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
    // Enriched (epic #14 / S5) — additive; absent on flat / old notes.
    sections?: NoteSectionFixture[];
    depth_tier?: DensityTier | null;
    magnitude?: NoteMagnitudeFixture | null;
    model_used?: string | null;
    validation_attempts?: number;
  } | null;
  // Enriched top-level density signal (schema_version 3); absent on old rows.
  magnitude?: NoteMagnitudeFixture | null;
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

/**
 * Two topical sections for the enriched (epic #14 / S6) render: each carries a
 * heading, its own `$`-math Markdown, and per-section concepts. The smoke
 * checks both headings render, the math becomes KaTeX, and the section nav
 * links resolve to the right anchors.
 */
export const SECTION_COSETS: NoteSectionFixture = {
  heading: "Cosets and Lagrange's theorem",
  markdown: `A subgroup $H \\le G$ partitions $G$ into **left cosets** $gH$.

$$
[G : H] = \\frac{|G|}{|H|}
$$
`,
  concepts: ["Cosets", "Lagrange's theorem"],
};

export const SECTION_CHAIN_RULE: NoteSectionFixture = {
  heading: "The chain rule",
  markdown: `For $f(g(x))$ the derivative is $f'(g(x)) \\cdot g'(x)$.

- Differentiate the outer function.
- Multiply by the derivative of the inner.
`,
  concepts: ["Chain rule", "Differentiation"],
};

/**
 * A substantial, sectioned, magnitude-aware note (schema_version 3) — the
 * enriched render path: a "deep" depth tier, multiple topical sections, and a
 * `NoteMagnitude` the badge reads. Override any field.
 */
export function sectionedNote(
  overrides: Partial<DailyNoteFixture> = {}
): DailyNoteFixture {
  const magnitude: NoteMagnitudeFixture = {
    transcript_chars: 5200,
    page_count: 6,
    page_chars: 9100,
    density_tier: "deep",
    duration_seconds: 312,
  };
  return dailyNote({
    synthesis: {
      // Flat markdown stays populated for back-compat; sections take priority.
      markdown: "## Overview\n\nA dense session across two topics.",
      concepts: [
        "Cosets",
        "Lagrange's theorem",
        "Chain rule",
        "Differentiation",
      ],
      summary: "A deep session: cosets/Lagrange, then the chain rule.",
      sections: [SECTION_COSETS, SECTION_CHAIN_RULE],
      depth_tier: "deep",
      magnitude,
      model_used: "claude-opus-mock",
      validation_attempts: 1,
    },
    magnitude,
    schema_version: 3,
    ...overrides,
  });
}

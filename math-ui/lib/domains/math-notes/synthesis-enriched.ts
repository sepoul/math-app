/**
 * LOCAL mirror of the backend's enriched `NoteSynthesis` shape (epic #14 / S5).
 *
 * The regenerated `@sepoul-packages/sdk` types for the enriched synthesis
 * (`sections` + `depth_tier` + embedded `magnitude`) do NOT exist yet: that
 * needs an operator to run `aiplatform declare-artifacts`, regenerate the SDK
 * from the platform's OpenAPI, and publish a new `@sepoul-packages/sdk` — none
 * of which can happen from the UI. Until then we render against these
 * hand-mirrored types, which match the backend definitions in
 * `packages/math-notes/src/mathai/math_notes/artifacts.py` field-for-field.
 *
 * TODO(#20): once the SDK is regenerated, replace these with the SDK schema
 * types — `S["NoteSynthesis"]`, `S["NoteSection"]`, `S["NoteMagnitude"]` (and
 * add `magnitude` to the `DailyNoteArtifact` derivation in `./types.ts`) — and
 * delete this file. All the call sites are typed against the names exported
 * here, so the swap is local to this module + `./types.ts`.
 */

/** Coarse content-volume bucket — mirrors backend `DensityTier`. */
export type DensityTier = "brief" | "standard" | "deep";

/**
 * Mirrors backend `NoteMagnitude` — the fused multi-modal density signal a
 * note's synthesis depth was scaled to. `page_count` is the strongest study-
 * scope proxy; `duration_seconds` is a minor, often-absent audio signal.
 */
export interface NoteMagnitude {
  transcript_chars: number;
  page_count: number;
  page_chars: number;
  density_tier: DensityTier;
  duration_seconds?: number | null;
}

/**
 * Mirrors backend `NoteSection` — one topical section of a note's synthesis:
 * a heading, its prose + KaTeX-validated Markdown, and the concepts it touches.
 */
export interface NoteSection {
  heading: string;
  markdown: string;
  concepts: string[];
}

/**
 * Mirrors the enriched backend `NoteSynthesis`. The flat fields
 * (`markdown` / `concepts` / `summary`) match the current SDK
 * `S["NoteSynthesis"]`; `sections` / `depth_tier` / `magnitude` are the
 * additive S5 enrichment the SDK does not yet expose. All enrichment fields
 * are optional, so a short/old note (flat `markdown` only) is a valid value.
 *
 * Note: `study_scope_hint` ("~4 hours on X", stated by the learner) lives on
 * the in-flight `SynthesisPlan`, which is NOT persisted on the artifact — so it
 * is intentionally absent here. The persisted study-scope proxy the badge uses
 * is `magnitude.page_count` (the documented strongest scope signal).
 */
export interface EnrichedNoteSynthesis {
  markdown?: string | null;
  concepts?: string[];
  summary?: string | null;
  sections?: NoteSection[];
  depth_tier?: DensityTier | null;
  magnitude?: NoteMagnitude | null;
  model_used?: string | null;
  validation_attempts?: number;
}

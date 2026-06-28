/**
 * Math-notes domain types — derived from the OpenAPI schema, NOT
 * hand-rolled (see AGENTS.md).
 *
 * `DailyNoteArtifact` and `MediaRef` only exist in the schema after the
 * contract-first dev loop has run against a local stack:
 *
 *   1. pip install -e packages/math-notes --no-deps   (so control imports)
 *   2. aiplatform declare-artifacts --bundle packages/math-notes/bundle.toml
 *   3. OPENAPI_SOURCE=http://localhost:8000/openapi.json \
 *        npm --prefix ../../ai-platform/sdk-ts run gen:api
 *
 * Until step 3 regenerates `schema.d.ts`, `tsc` will (correctly) flag
 * these as missing. That's the intended order — build the contract,
 * then the types light up.
 */
import type { components } from "@sepoul-packages/sdk";

type S = components["schemas"];

type Required_<T, K extends keyof T> = Omit<T, K> & {
  [P in K]-?: NonNullable<T[P]>;
};

/**
 * A captured study note — now a self-contained document. `pages` holds the
 * raw per-photo extraction (faithful transcription) and `synthesis` the
 * cleaned-up, note-level math (markdown + KaTeX-validated LaTeX). Old rows
 * (pre-redesign, `schema_version` 1) still hydrate, with `synthesis` null and
 * `pages` empty. `storage_url` is hydrated by `GET /artifacts/{id}`.
 */
export type DailyNoteArtifact = Required_<
  S["DailyNoteArtifact"],
  "artifact_id" | "created_at" | "note_date"
>;

/**
 * Faithful raw extraction of one notebook photo, embedded inline on the note
 * (`DailyNoteArtifact.pages`). Raw-only: `raw_text` is what's on the page; the
 * math is reconstructed note-level in `synthesis`. Supersedes the legacy
 * per-photo `note_page` artifact, which is no longer minted.
 */
export type NotePage = S["NotePage"];

/**
 * The note-level synthesis: one coherent, always-correct view of the math.
 * `markdown` is the canonical flat document (prose + KaTeX-validated LaTeX),
 * with note-level `concepts` and a `summary`. Enriched (epic #14, S5) so a
 * substantial session is more than one flat blob: `sections` carries per-topic
 * structure, `depth_tier` marks how deep it rendered, and `magnitude` embeds
 * the fused density signal the depth was scaled to — all additive, so short or
 * pre-enrichment notes (flat `markdown` only) stay valid.
 */
export type NoteSynthesis = S["NoteSynthesis"];

/**
 * One topical section of an enriched synthesis: a heading, its prose +
 * KaTeX-validated Markdown, and the concepts it touches.
 */
export type NoteSection = S["NoteSection"];

/**
 * The fused multi-modal density signal a note's synthesis depth was scaled to.
 * `page_count` is the strongest study-scope proxy; `duration_seconds` is a
 * minor, often-absent audio signal.
 */
export type NoteMagnitude = S["NoteMagnitude"];

/** Coarse content-volume bucket the synthesis depth is keyed off. */
export type DensityTier = NonNullable<NoteMagnitude["density_tier"]>;

/** Response of `POST /media`. */
export type MediaRef = S["MediaRef"];

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
import type { components } from "@aiplatform/sdk";

type S = components["schemas"];

type Required_<T, K extends keyof T> = Omit<T, K> & {
  [P in K]-?: NonNullable<T[P]>;
};

/** A captured study note. `storage_url` is hydrated by `GET /artifacts/{id}`. */
export type DailyNoteArtifact = Required_<
  S["DailyNoteArtifact"],
  "artifact_id" | "created_at" | "note_date"
>;

/** Response of `POST /media`. */
export type MediaRef = S["MediaRef"];

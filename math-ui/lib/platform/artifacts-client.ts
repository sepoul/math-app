/**
 * Thin wrapper over `@sepoul-packages/sdk`'s `PlatformSession` for the
 * artifact read path. The PR-3 options — `offset` pagination, `fields`
 * (whitelisted domain-field equality filters), full projection, and
 * batch hydration — are now first-class SDK methods, so these are plain
 * delegations (the earlier BFF-direct shim is gone).
 */
import { platformSession } from "@/lib/session";
import type {
  Artifact,
  ArtifactListResponse,
  ArtifactTypeListResponse,
  FullArtifactListResponse,
} from "./artifacts-types";

export type { FullArtifactListResponse } from "./artifacts-types";

export interface ListArtifactsParams {
  jobId?: string;
  artifactType?: string;
  limit?: number;
  /** PR-3c: pagination offset (stable created_at desc). */
  offset?: number;
  /** PR-3b: equality filters on whitelisted domain fields, e.g.
   * `source_note_id`. A field not declared on the type → 400. */
  [field: string]: string | number | boolean | undefined;
}

/** Split our flat params into the SDK's `{ jobId, artifactType, limit,
 * offset, fields }` shape — anything beyond the known envelope keys is a
 * domain-field filter and goes under `fields`. */
function toOpts(params: ListArtifactsParams) {
  const { jobId, artifactType, limit, offset, ...rest } = params;
  const fields: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(rest)) {
    if (v !== undefined) fields[k] = v;
  }
  return {
    jobId,
    artifactType,
    limit,
    offset,
    ...(Object.keys(fields).length ? { fields } : {}),
  };
}

/** Summary list (cheap projection — no domain fields). */
export function fetchArtifacts(
  params: ListArtifactsParams = {}
): Promise<ArtifactListResponse> {
  return platformSession().listArtifacts(toOpts(params));
}

/** Full-projection list (PR-3a) — full typed artifacts inline
 * (concepts/latex/text, storage_url hydrated). */
export function fetchArtifactsFull(
  params: ListArtifactsParams = {}
): Promise<FullArtifactListResponse> {
  return platformSession().listArtifactsFull(toOpts(params));
}

/** Hydrate many artifacts by id in one round-trip (PR-3d). */
export function batchGetArtifacts(ids: string[]): Promise<Artifact[]> {
  if (ids.length === 0) return Promise.resolve([]);
  return platformSession().batchGetArtifacts(ids);
}

/**
 * Calls the legacy `/artifacts/types` registry endpoint, not the new
 * `/artifact-types` catalog.
 */
export function fetchArtifactTypes(): Promise<ArtifactTypeListResponse> {
  return platformSession().listArtifactTypesRegistry();
}

export function fetchArtifact(id: string): Promise<Artifact> {
  return platformSession().getArtifact(id) as Promise<Artifact>;
}

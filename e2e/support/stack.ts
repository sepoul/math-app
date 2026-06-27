/**
 * Live-stack helpers for the `live` project.
 *
 * The platform stack (API :8000 + workers) is operator-driven — Playwright's
 * `webServer` starts the math-ui dev server but not the stack. So each live
 * spec calls `skipUnlessStackUp()` in a `beforeAll`, which health-checks the
 * stack once (cached) and **skips with a clear message** if it's down. That's
 * what keeps a `mock`-only run from ever failing for a missing backend.
 */
import { request as pwRequest, test, type APIRequestContext } from "@playwright/test";

const API_URL = process.env.MATH_API_URL ?? "http://localhost:8000";
const UI_URL = process.env.MATH_UI_URL ?? "http://localhost:3000";

/** Domains the live journeys exercise; their JobDefinitions must be in the catalog. */
const REQUIRED_DOMAINS = ["math_qa", "math_notes"];

export interface StackStatus {
  up: boolean;
  reason?: string;
  warnings: string[];
}

let cached: Promise<StackStatus> | undefined;

async function probe(): Promise<StackStatus> {
  const warnings: string[] = [];
  let api: APIRequestContext;
  try {
    api = await pwRequest.newContext();
  } catch (e) {
    return { up: false, reason: `could not create request context: ${String(e)}`, warnings };
  }
  try {
    // 1. Platform API health.
    let health;
    try {
      health = await api.get(`${API_URL}/health`, { timeout: 5_000 });
    } catch (e) {
      return { up: false, reason: `platform API ${API_URL} unreachable (${String(e)})`, warnings };
    }
    if (!health.ok()) {
      return { up: false, reason: `GET ${API_URL}/health → ${health.status()}`, warnings };
    }

    // 2. Catalog lists the domains the journeys need.
    const defsResp = await api.get(`${API_URL}/job-definitions`, { timeout: 5_000 });
    if (!defsResp.ok()) {
      return { up: false, reason: `GET ${API_URL}/job-definitions → ${defsResp.status()}`, warnings };
    }
    const defs = (await defsResp.json()) as Array<{ name?: string }>;
    const names = new Set(defs.map((d) => d.name));
    const missing = REQUIRED_DOMAINS.filter((d) => !names.has(d));
    if (missing.length) {
      return {
        up: false,
        reason: `catalog missing job-definitions: ${missing.join(", ")}`,
        warnings,
      };
    }

    // 3. math-ui dev server up.
    try {
      const ui = await api.get(UI_URL, { timeout: 5_000 });
      if (!ui.ok()) warnings.push(`math-ui ${UI_URL} → ${ui.status()}`);
    } catch (e) {
      return { up: false, reason: `math-ui ${UI_URL} unreachable (${String(e)})`, warnings };
    }

    // Soft note: validate_latex (used by the notes synthesis) only runs if the
    // worker's UI_TOOL_API_URL points at the host UI. We can't introspect the
    // worker from here, so we just remind — a missing reach silently no-ops
    // latex validation (the note still renders, math may be unvalidated).
    warnings.push(
      "live: ensure the default worker's UI_TOOL_API_URL points at the host UI " +
        "(http://host.docker.internal:3000) so validate_latex runs during synthesis."
    );
    return { up: true, warnings };
  } finally {
    await api.dispose();
  }
}

export function stackStatus(): Promise<StackStatus> {
  return (cached ??= probe());
}

/**
 * Call in a live spec's `beforeAll`. Health-checks the stack once and skips
 * the whole file (with the reason) if it's down; otherwise prints warnings.
 */
export async function skipUnlessStackUp(): Promise<void> {
  const s = await stackStatus();
  for (const w of s.warnings) console.warn(`[live] ${w}`);
  test.skip(!s.up, s.reason ? `live stack down — ${s.reason}` : "live stack down");
}

/** Newest daily_note (platform returns stable created_at desc), or null. */
export async function latestNote(
  api: APIRequestContext
): Promise<{ id: string; created_at: string } | null> {
  const r = await api.get(
    `${API_URL}/artifacts?artifact_type=daily_note&limit=1&full=true`
  );
  if (!r.ok()) return null;
  const data = (await r.json()) as { artifacts?: Array<{ artifact_id: string; created_at: string }> };
  const a = data.artifacts?.[0];
  return a ? { id: a.artifact_id, created_at: a.created_at } : null;
}

/**
 * Poll the catalog until a daily_note newer than `baselineCreatedAt` appears
 * (a note minted after we hit Save), and return its id. The capture job can
 * outlast the record page's own poll, so the test waits here independently.
 */
export async function waitForNewNote(
  api: APIRequestContext,
  baselineCreatedAt: string | null,
  opts: { timeoutMs?: number; pollMs?: number } = {}
): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? 230_000;
  const pollMs = opts.pollMs ?? 3_000;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const latest = await latestNote(api);
    if (latest && latest.created_at !== baselineCreatedAt) return latest.id;
    await new Promise((r) => setTimeout(r, pollMs));
  }
  throw new Error(
    `no new daily_note appeared within ${timeoutMs}ms (baseline ${baselineCreatedAt ?? "none"})`
  );
}

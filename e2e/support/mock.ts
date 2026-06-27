/**
 * `mockPlatform(page, options)` — intercept every BFF `/api/**` call the
 * browser makes and answer it from fixtures, so the `mock` project needs no
 * platform stack. Mirrors the endpoints math-ui hits through
 * `@sepoul-packages/sdk`'s `PlatformSession` (base `/api`):
 *
 *   GET  /api/artifacts?…&full=true   → { artifacts, total }  (full projection)
 *   GET  /api/artifacts?…             → { artifacts, total }  (summary projection)
 *   GET  /api/artifacts/types         → { artifact_types: [] }
 *   POST /api/artifacts/batch         → Artifact[]
 *   GET  /api/artifacts/<id>          → one artifact            (or 404)
 *   POST /api/jobs/runs/submit        → { job_id }              (body captured)
 *   GET  /api/jobs                    → JobStatusResponse[]
 *   GET  /api/jobs/<id>               → JobStatusResponse        (SUCCEEDED)
 *   POST /api/media                   → MediaRef
 *   GET  /api/media/**                → 1×1 PNG (so <img>/<audio> don't error)
 *   GET  /api/workflows               → { workflows: [] }
 *   *                                 → {}  (permissive fallback)
 */
import type { Page, Route } from "@playwright/test";
import type { DailyNoteFixture } from "../fixtures/artifacts";

/** A 1×1 transparent PNG — returned for any /api/media/** GET. */
const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
  "base64"
);

export interface SubmittedJob {
  job_type: string;
  [field: string]: unknown;
}

export interface MockOptions {
  /** daily_note rows returned by the list endpoint (full + summary). */
  notes?: DailyNoteFixture[];
  /** Extra artifacts addressable by id at GET /artifacts/<id> (merged with `notes`). */
  artifactById?: Record<string, unknown>;
  /** Ids that should 404 at GET /artifacts/<id> (the miss case). */
  missingIds?: string[];
  /** Terminal status returned by GET /jobs/<id> (default SUCCEEDED). */
  jobStatus?: string;
}

export interface MockHandle {
  /** Bodies of every POST /api/jobs/runs/submit, in order. */
  submissions: SubmittedJob[];
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function summary(n: DailyNoteFixture) {
  return {
    artifact_id: n.artifact_id,
    artifact_type: n.artifact_type,
    created_at: n.created_at,
    created_by_job: n.created_by_job ?? null,
  };
}

export async function mockPlatform(
  page: Page,
  options: MockOptions = {}
): Promise<MockHandle> {
  const notes = options.notes ?? [];
  const byId = new Map<string, unknown>();
  for (const n of notes) byId.set(n.artifact_id, n);
  for (const [id, a] of Object.entries(options.artifactById ?? {})) byId.set(id, a);
  const missing = new Set(options.missingIds ?? []);
  const handle: MockHandle = { submissions: [] };

  await page.route(/\/api\//, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();

    // ---- media ----
    if (path === "/api/media" && method === "POST") {
      return json(route, {
        storage_ref: `mock-ref-${handle.submissions.length}-${Date.now()}`,
        filename: "upload",
        content_type: "application/octet-stream",
        byte_size: 1234,
      });
    }
    if (path.startsWith("/api/media/")) {
      return route.fulfill({ status: 200, contentType: "image/png", body: PNG_1x1 });
    }

    // ---- jobs ----
    if (path === "/api/jobs/runs/submit" && method === "POST") {
      try {
        handle.submissions.push(req.postDataJSON() as SubmittedJob);
      } catch {
        /* non-JSON body — ignore for capture */
      }
      return json(route, { job_id: `mock-job-${handle.submissions.length}` });
    }
    if (path === "/api/jobs") {
      return json(route, []);
    }
    if (path.startsWith("/api/jobs/")) {
      const jobId = path.slice("/api/jobs/".length);
      return json(route, {
        job_id: jobId,
        job_type: "math_notes",
        status: options.jobStatus ?? "SUCCEEDED",
        stage: null,
        percent: 100,
        message: null,
        waiting_for: null,
        error_message: null,
        result: null,
      });
    }

    // ---- artifacts ----
    if (path === "/api/artifacts/types") {
      return json(route, { artifact_types: [] });
    }
    if (path === "/api/artifacts/batch" && method === "POST") {
      let ids: string[] = [];
      try {
        ids = (req.postDataJSON() as { ids?: string[] }).ids ?? [];
      } catch {
        /* ignore */
      }
      return json(route, ids.map((id) => byId.get(id)).filter(Boolean));
    }
    if (path === "/api/artifacts") {
      const full = url.searchParams.get("full") === "true";
      return json(route, {
        artifacts: full ? notes : notes.map(summary),
        total: notes.length,
      });
    }
    if (path.startsWith("/api/artifacts/")) {
      const id = path.slice("/api/artifacts/".length);
      if (missing.has(id) || !byId.has(id)) {
        return json(route, { detail: `Artifact not found: ${id}` }, 404);
      }
      return json(route, byId.get(id));
    }

    // ---- catalog reads used by the nav routes ----
    if (path === "/api/workflows") {
      return json(route, { workflows: [] });
    }

    // ---- permissive fallback ----
    return json(route, {});
  });

  return handle;
}

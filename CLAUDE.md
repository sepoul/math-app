# CLAUDE.md — math-app

Orientation for future sessions. Read this before reasoning about "how does
anything run / deploy here."

## The one big idea: this repo is infrastructure-free

`math-app` ships **domain wheels** into a separate platform. It has **no
servers, no infra, no runtime of its own**. There is nothing to "run" here in
the prod sense — you build a wheel and register it with a running
**ai-platform** instance via a CLI. The platform is the thing that has workers,
a database, storage, and an API.

- **This repo** = the *math domain*: job types + their artifacts + a Next.js UI.
- **The platform** (sibling checkout at `../ai-platform`) = a thin, domain-free
  orchestrator: a catalog (`CodePackage` / `JobDefinition` / `ArtifactType`
  rows), workers that **pip-install domain wheels at boot**, a blob/storage
  plane, and a typed TS SDK (`@aiplatform/sdk`) the UI consumes.

If you're tempted to add a Dockerfile/compose/server to *this* repo for a
backend domain — don't. The backend ships as a wheel. (The only image this repo
builds is the `math-ui` Next.js app.)

## Layout

```
packages/math-qa/            default runtime  (pydantic_ai + Anthropic + Logfire)
packages/math-notes/         default runtime  (daily-notes ingest: audio + photos)
packages/math-conversation/  crewai runtime   (crewai[anthropic])
math-ui/                     Next.js domain UI (drives jobs via @aiplatform/sdk)
docs/                        design proposals (math-conversation.md, etc.)
```

Each backend package is a domain: `src/mathai/<domain>/` with the standard
files — `control.py` (schemas, engine-free, imported by the API), `execution.py`
(graph + persistence, imported by the worker), `workflow.py` (pydantic_graph
nodes), `state.py`, `models.py`, `artifacts.py` — plus a `pyproject.toml` and a
`bundle.toml`.

## Two runtimes

A *runtime* is an isolated dependency environment; a worker serves exactly one.
The split exists because of an OpenTelemetry pin conflict (Logfire ≥1.39 vs
CrewAI <1.35) — they can't share an interpreter.

| Runtime   | Stack                                   | Domains                      |
|-----------|-----------------------------------------|------------------------------|
| `default` | pydantic_graph + pydantic_ai + Logfire  | `math_qa`, `math_notes`, API |
| `crewai`  | pydantic_graph + crewai[anthropic]      | `math_conversation`          |

A package's runtime is declared in its `bundle.toml` (`runtime = "default"`).

## The deploy loop (this is "how it works")

The platform is **API-first**. Deploy = build a wheel, then push it + its
catalog rows to a running platform with the `aiplatform` CLI (ships with
`aiplatform-core`).

```bash
# 1. Bump the version in BOTH places (they must match):
#      packages/<pkg>/pyproject.toml   -> version = "0.1.3"
#      packages/<pkg>/bundle.toml      -> version + the wheel = "dist/...-0.1.3-...whl" path
# 2. Build the wheel:
cd packages/<pkg> && uv build --wheel       # -> dist/<name>-<ver>-py3-none-any.whl
# 3. Push it + register the catalog rows:
aiplatform deploy --bundle packages/<pkg>/bundle.toml --api-url http://localhost:8000
```

`aiplatform deploy` does, in order (all **idempotent on `(name, version)`**):
1. **CodePackage** — multipart-uploads the wheel to `/code-packages`.
2. **JobDefinition** — imports the bundle's `control_entrypoint` *in-process*,
   derives the job's input/result schemas, POSTs to `/job-definitions`.
3. **ArtifactType** — POSTs each artifact's JSON Schema to `/artifact-types`.

`package.version` drives the version of all three. The `execution_entrypoint`
is **not** imported at deploy time — it's recorded on the JobDefinition row and
imported by the *worker* after it installs the wheel.

Other CLI subcommands:
- `aiplatform declare-artifacts --bundle … --api-url …` — register **only** the
  artifact types (the contract), no wheel/job. Contract-first: lets the SDK
  regenerate so UI + backend build in parallel before the job exists.
- `aiplatform snapshot-openapi --api-url …` — dump `/openapi.json` to a file for
  SDK regen.

After deploy, regenerate SDK types if you added/changed an artifact or schema:
`OPENAPI_SOURCE=http://localhost:8000/openapi.json npm --prefix ../ai-platform/sdk-ts run gen:api`.

## Operational facts that will bite you

- **Workers install wheels at boot, not on deploy.** Deploying a new version
  updates the catalog and uploads the wheel, but a *running* worker keeps using
  the version it installed at boot (look for `Installed N CodePackage(s) at
  boot` in its log). **To load new code, restart the worker** for that runtime
  (`docker restart ai-platform-worker-1` for `default`). Confirm with the boot
  log line `Installed CodePackage <name>@<ver>`.
- **Local vs CI/prod — don't conflate them.** CI here is **publish-only**: it
  builds + pushes the `math-ui` image to GHCR and does **not** deploy. Backend
  deploy is operator-driven (`aiplatform deploy`). Docs/comments that mention
  GitHub Actions, Hetzner, tailnet, `mathapp-prod` are about the prod path —
  **ignore them for local work**; just deploy against `http://localhost:8000`.
- **The CLI imports your control module in-process**, so the package *and*
  `ai_platform` must be importable in the venv running the CLI. The platform's
  `../ai-platform/.venv` editable installs can point at a stale path (a
  no-longer-existing `mathapp/` checkout) — if `import ai_platform` fails there,
  run the CLI with an explicit `PYTHONPATH` at the real source roots instead of
  fighting the venv:
  ```bash
  PYTHONPATH="../ai-platform/packages/core/src:../ai-platform/packages/worker/src:../ai-platform/packages/api/src:packages/<pkg>/src" \
    ../ai-platform/.venv/bin/python -m ai_platform.bundle.cli deploy \
      --bundle packages/<pkg>/bundle.toml --api-url http://localhost:8000
  ```
  (Putting the package's own `src` first also makes the deploy introspect your
  *edited* source rather than an installed wheel.)
- **Version selection on submit is not naive max-semver.** A stray high version
  (e.g. a stub `1.0.0`) does not necessarily shadow your latest real deploy —
  check what the worker actually installs in its boot log.

## The platform/domain boundary (design §13)

The platform owns **catalog + orchestration + bytes** (it stores blobs and
refs, runs the graph, persists artifacts). Domains own **compute + data +
interpretation**. Consequences you'll feel:

- Anything that *interprets* media (ASR, vision/OCR, RAG, embeddings) is
  domain-side. The platform provides **generic provider helpers** in the worker
  base that domains call from their own nodes — e.g.
  `ai_platform.ai.providers.audio.AudioInterpreter` (storage_ref → text via
  OpenAI) and `…providers.vision.ImageInterpreter` (storage_ref → text). These
  are **text-in/text-out and generic**: if you want structured output (LaTeX,
  concepts), prompt for JSON and parse it **in your domain node**, not in the
  helper.
- Artifacts are only minted by jobs (there is no `POST /artifacts`). To add a
  new artifact type, define a `BaseArtifact` subclass, register it in the
  domain's `*_ARTIFACTS` dict (so `control.py` publishes its schema), and bump +
  deploy.

## Local dev loop, condensed

```bash
# platform running in compose (../ai-platform): API :8000, worker-1 (default), worker-crewai-1
curl -s http://localhost:8000/job-definitions   # see the catalog
# edit a domain under packages/<pkg>/src/mathai/<domain>/ ...
# bump version (pyproject + bundle), uv build --wheel, aiplatform deploy (see above)
docker restart ai-platform-worker-1              # load the new default-runtime wheel
# verify: /job-definitions, /artifact-types show the new version
```

## math-ui + the typed SDK

The UI consumes typed shapes from the SDK — `components["schemas"]` (e.g.
`S["NotePageArtifact"]`). The SDK is a **published npm package,
`@sepoul-packages/sdk`** (public npmjs, no auth), generated + released by
`../ai-platform` from its OpenAPI. math-app just depends on it like any
package:

- `package.json`: `"@sepoul-packages/sdk": "^0.1.1"`.
- New schema/types after the platform ships a version: `npm --prefix math-ui
  update @sepoul-packages/sdk` (new versions release on `sdk-v*` tags).
- The PR-3 read path is first-class on the SDK's `PlatformSession`:
  `listArtifacts(opts)` (envelope + `offset` + `fields` domain filters),
  `listArtifactsFull(opts)` (full typed artifacts inline), `batchGetArtifacts(ids)`.
  `math-ui/lib/platform/artifacts-client.ts` wraps these (`fetchArtifacts` /
  `fetchArtifactsFull` / `batchGetArtifacts`).

**History (don't recreate it):** the SDK used to be a local
`file:../../ai-platform/sdk-ts` dep that npm *copied* (not symlinked) into
`node_modules`, so regenerating the source didn't update the copy the UI
resolved → phantom `Property 'X' does not exist on type { …schemas… }` errors,
and a broken SDK `tsc` could even block `npm run dev` (it ran `sdk:build` in
`predev`). All of that is gone with the npm package — no `predev`/`sdk:build`
hooks, no `.npmrc install-links` workaround.

**Related local-dev fact:** the `validate_latex` / `validate_figure` agent tools
(used by `math_qa`, and now `math_notes`' page parse) POST to the **math-ui
Node server**, read from `UI_TOOL_API_URL` (compose default
`http://math-ui:7860`; a host-run UI is reached via `http://host.docker.internal:3000`).
If the worker can't reach it, `latex`/figure validation silently no-ops (stores
nothing rather than guessing) — so a job can "succeed" with empty `latex` purely
because math-ui was down. Confirm reachability from *inside* the worker:
`docker exec ai-platform-worker-1 curl -s "$UI_TOOL_API_URL/api/tools/validate-latex" ...`.

## See also

- `README.md` — short public-facing version of the above.
- `../ai-platform/packages/core/src/ai_platform/bundle/` — the deploy CLI +
  `deploy_bundle` / `declare_artifacts` internals and `bundle.toml` schema
  (`manifest.py`).
- `docs/math-conversation.md` — example of a full domain design proposal.
- Memory: `math-app-platform-split`, `math-app-feature-roadmap`.


## NEXT topic, remind me w start here please

Implement a Markdown + math rendering migration for daily notes.

Context:
- daily_note artifacts store the main document at synthesis.markdown.
- The database/schema should remain unchanged: synthesis.markdown stays a string.
- Existing notes use LaTeX delimiters:
  - inline: \( ... \)
  - display: \[ ... \]
- New notes should use one canonical Markdown-math format:
  - inline: $...$
  - display: $$...$$
- The current frontend Latex component renders math but does not parse Markdown, so headings such as ##, bold text, and normal Markdown structure display literally.

Please make the following changes.

1. In-place migration for existing stored notes

Create a safe, idempotent backend migration or one-off migration command that updates existing daily_note records in place.

For every artifact where synthesis.markdown is a non-empty string:

- Convert inline delimiters:
  - \( becomes $
  - \) becomes $
- Convert display delimiters:
  - \[ becomes $$
  - \] becomes $$
- Do not alter any other artifact fields.
- Do not alter records without synthesis.markdown.
- Make the migration safe to run more than once. After the first conversion, rerunning it should produce no further changes.
- Log/report:
  - number of artifacts scanned
  - number updated
  - number skipped
  - failures with artifact IDs, without stopping the whole migration
- Follow the repository’s existing conventions for DB access, migrations, scripts, transactions, and JSON/JSONB updates.
- Prefer a dry-run mode if that fits existing project conventions.

Before writing the migration, inspect how daily_note artifacts and the synthesis object are persisted. Do not invent a new table, schema column, or storage layer.

2. Future synthesis generation

Update the prompt/schema/instructions used to generate synthesis.markdown so all future notes use standard Markdown plus dollar-delimited TeX.

Add rules equivalent to:

Write clean GitHub-style Markdown.

Math formatting:
- Use $...$ for inline math.
- Use $$...$$ for display math, with the opening and closing delimiters on their own lines.
- Never use \( ... \), \[ ... \], raw HTML, Unicode superscripts/subscripts as math substitutes, or fragmented math across lines.
- Keep TeX source valid and readable.

Generated content should look conceptually like:

## Cosets

Let $G$ be a group and $H \le G$ a subgroup.

$$
gH = \{\, gh : h \in H \,\}.
$$

**Claim.** $N \trianglelefteq G$ if and only if $gN = Ng$ for every $g \in G$.

3. Frontend rendering

Replace the current LaTeX-only rendering path for synthesis.markdown with standard React Markdown rendering plus KaTeX math support.

Use this minimal conventional stack:
- react-markdown
- remark-math
- rehype-katex
- katex

Only add remark-gfm if existing notes actually need GitHub-flavored Markdown features such as tables or task lists.

Requirements:
- Do not use dangerouslySetInnerHTML.
- Import KaTeX CSS once in the appropriate app-level or component-level location for this codebase.
- Preserve current typography, layout conventions, and Tailwind styling.
- Headings, bold text, paragraphs, lists, inline math, and display math must render correctly.
- Do not break the transcript or raw-page fallback views.
- Do not retain a custom Markdown parser unless the repository already has a strong reason for one.

4. Validation

Add focused tests if this repository has test infrastructure:

- Existing \( ... \) and \[ ... \] note content migrates to $...$ and $$...$$.
- The migration is idempotent.
- Markdown headings and bold text render as semantic HTML.
- Inline and display TeX render through KaTeX.
- Existing artifacts with no synthesis.markdown remain unchanged.

At the end, summarize:
1. files changed
2. how to run the migration
3. whether a dry run is available
4. any existing records that could not be migrated
5. package additions
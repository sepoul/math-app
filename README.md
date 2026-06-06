# math-app

The math domain for the [ai-platform](https://github.com/sepoul/ai-platform).

Lives in its own repo so the platform stays domain-free. The platform
is a thin orchestrator: catalogs (JobDefinitions, ArtifactTypes,
CodePackages), a worker that pip-installs domain wheels at boot, and a
typed TS SDK that any domain UI consumes. This repo carries the math
side of that: two backend job types (`math_qa`, `math_conversation`)
and `math-ui`, a Next.js app that uses `@aiplatform/sdk` to drive them.

```
packages/math-qa/             # default-runtime: pydantic_ai + Anthropic + Logfire
packages/math-conversation/   # crewai runtime: crewai[anthropic]
math-ui/                      # Next.js domain UI
```

## Deploy to a running platform

```bash
# Build both wheels
cd packages/math-qa && uv build --wheel
cd ../math-conversation && uv build --wheel

# Push them + their catalog rows
aiplatform deploy --bundle packages/math-qa/bundle.toml \
    --api-url https://your-platform:8000
aiplatform deploy --bundle packages/math-conversation/bundle.toml \
    --api-url https://your-platform:8000
```

The platform's worker(s) install the wheel on next boot
(`install_packages_for_runtime`); its API auto-discovers the new
JobDefinitions from the catalog.

CI does this automatically on push to `main` — see
[.github/workflows/deploy.yml](.github/workflows/deploy.yml).

## math-ui

```bash
cd math-ui
npm install
PLATFORM_API_URL=https://your-platform:8000 npm run dev
```

Reads everything via `@aiplatform/sdk` (the BFF proxy at `/api/*`
forwards to the upstream). No domain knowledge in the SDK — math
shapes (LaTeX, figures, conversation panels) all live in `math-ui/`.

## See also

- [ai-platform](https://github.com/sepoul/ai-platform) — the platform repo
- [ai-platform/docs/architecture.md](https://github.com/sepoul/ai-platform/blob/main/docs/architecture.md) — system overview
- [ai-platform/NEXT_BEST_STEPS.md §7q](https://github.com/sepoul/ai-platform/blob/main/NEXT_BEST_STEPS.md) — the repo-split plan that produced this repo

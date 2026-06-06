# Build context: the math-app workspace ROOT, with ai-platform/
# cloned as a sibling. The CI workflow (.github/workflows/deploy.yml)
# does the clone before docker build. Inside the build:
#   /app/ai-platform/sdk-ts/   ← cloned from sepoul/ai-platform
#   /app/math-app/math-ui/     ← this repo

# ---------- sdk build ----------
FROM node:20-alpine AS sdk
WORKDIR /sdk

RUN apk add --no-cache libc6-compat

COPY ai-platform/sdk-ts/package.json ai-platform/sdk-ts/package-lock.json* ./
RUN \
  if [ -f package-lock.json ]; then npm ci --ignore-scripts; \
  else npm i --ignore-scripts; \
  fi

COPY ai-platform/sdk-ts/tsconfig.json ./
COPY ai-platform/sdk-ts/scripts ./scripts
COPY ai-platform/sdk-ts/src ./src
RUN npm run build

# ---------- deps ----------
FROM node:20-alpine AS deps
WORKDIR /app

RUN apk add --no-cache libc6-compat

# Mirror the local-dev sibling layout: ai-platform/ next to math-app/.
COPY math-app/math-ui/package.json math-app/math-ui/package-lock.json* math-app/math-ui/.npmrc* ./math-app/math-ui/
COPY --from=sdk /sdk ./ai-platform/sdk-ts

WORKDIR /app/math-app/math-ui
RUN \
  if [ -f package-lock.json ]; then npm ci --ignore-scripts; \
  else npm i --ignore-scripts; \
  fi

# ---------- next build ----------
FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/math-app/math-ui/node_modules ./math-app/math-ui/node_modules
COPY --from=sdk /sdk ./ai-platform/sdk-ts
COPY math-app/math-ui ./math-app/math-ui

WORKDIR /app/math-app/math-ui
RUN npm run build --ignore-scripts

# ---------- run ----------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=7860

EXPOSE 7860

# Standalone bootstrap is at /app/server.js; static at /app/.next/static.
# Lesson from ai-platform PR #20 + #21.
COPY --from=builder /app/math-app/math-ui/public ./public
COPY --from=builder /app/math-app/math-ui/.next/standalone ./
COPY --from=builder /app/math-app/math-ui/.next/static ./.next/static

HEALTHCHECK CMD wget -qO- http://127.0.0.1:7860/ || exit 1

CMD ["node", "server.js"]

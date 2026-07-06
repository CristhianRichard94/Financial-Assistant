---
name: pnpm-workspace
description: Use when working on the Node/TypeScript side of FinSight (artifacts/finsight, artifacts/api-server, scripts) - covers workspace layout, run/build/typecheck commands, and the frontend<->API routing gotcha.
---

# pnpm workspace — FinSight

This repo's TypeScript/Node code is a pnpm workspace, separate from the Python
services under `services/`.

## Layout

- `artifacts/finsight/` — Next.js 15 App Router frontend (port 23970)
- `artifacts/api-server/` — Express 5 API server (port 8080), owns all `/api/*` routes
- `scripts/` — misc TypeScript scripts, its own `package.json`
- Root `package.json` — workspace scripts only, no app code

## Commands

```bash
pnpm --filter @workspace/finsight run dev     # frontend dev server
pnpm --filter @workspace/api-server run dev   # API server dev
pnpm run typecheck                            # typecheck every package
pnpm run build                                # typecheck + build all packages
```

Always use `pnpm`, never `npm`/`yarn` — the root `preinstall` script hard-fails
on any other package manager.

## Routing gotcha (read before adding an API route)

The Express API server intercepts `/api/*` before Next.js in the deployed
Replit environment. Next.js `src/app/api/*` route handlers exist and work
correctly in local `next dev`, but may be unreachable in production depending
on which proxy is actually in front. **When adding or changing an `/api/*`
endpoint, mirror the logic in both places**:

- `artifacts/finsight/src/app/api/**/route.ts` (Next.js Route Handlers)
- `artifacts/api-server/src/routes/finsight.ts` (Express)

This is exactly what was done when wiring the frontend to the Python
`rag-api` service — see `artifacts/finsight/src/lib/ragApiClient.ts` and
`artifacts/api-server/src/lib/ragApiClient.ts`, which are near-duplicate
server-side clients kept in sync deliberately, not an oversight.

## State management

- `artifacts/api-server/src/lib/finSightStore.ts` — in-memory mock store for
  dashboard data (still mocked; out of scope for the RAG feature)
- Real document/chat data now flows through the Python `rag-api` service, not
  the in-memory store — see the `rag-api` skill.

## Gotchas

- `react-dropzone` requires `"use client"` (already applied in `DocumentsView`)
- Next.js dev server needs `PORT` env var, started with `next dev -p $PORT`
- To swap in a real database for dashboard data: replace `finSightStore.ts`
  with Drizzle-backed queries

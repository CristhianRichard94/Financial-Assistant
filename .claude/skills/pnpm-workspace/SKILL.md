---
name: pnpm-workspace
description: Use when working on the Node/TypeScript side of FinSight (artifacts/finsight, scripts) - covers workspace layout and run/build/typecheck commands.
---

# pnpm workspace — FinSight

This repo's TypeScript/Node code is a pnpm workspace, separate from the Python
services under `services/`.

## Layout

- `artifacts/finsight/` — Next.js 15 App Router frontend, also owns all
  `/api/*` routes via Next.js Route Handlers (`src/app/api/**`) (port 23970)
- `scripts/` — misc TypeScript scripts, its own `package.json`
- Root `package.json` — workspace scripts only, no app code

## Commands

```bash
pnpm --filter @workspace/finsight run dev     # frontend + API dev server
pnpm run typecheck                            # typecheck every package
pnpm run build                                # typecheck + build all packages
```

Always use `pnpm`, never `npm`/`yarn` — the root `preinstall` script hard-fails
on any other package manager.

## State management

- `artifacts/finsight/src/lib/store.ts` — in-memory mock store for dashboard
  data only (still mocked; out of scope for the RAG feature)
- Real document data flows through the Python `rag-api` service, not the
  in-memory store — see the `rag-api` skill.
- Real chat history is read/written directly against a Supabase
  `chat_messages` table via `src/app/api/chat/messages/route.ts` (per-user,
  enforced by Postgres RLS) — `rag-api` is only called per-message to
  generate the assistant's reply text, not to store the conversation.

## Gotchas

- `react-dropzone` requires `"use client"` (already applied in `DocumentsView`)
- Next.js dev server needs `PORT` env var, started with `next dev -p $PORT`
- To swap in a real database for dashboard data: replace `store.ts`
  with Drizzle-backed queries

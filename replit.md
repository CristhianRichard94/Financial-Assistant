# FinSight

AI-powered personal finance assistant that analyzes uploaded documents (PDFs, CSVs, images) and answers questions about your finances.

## Run & Operate

- `pnpm --filter @workspace/finsight run dev` — run the Next.js frontend (port 23970)
- `pnpm --filter @workspace/api-server run dev` — run the API server (port 8080)
- `pnpm run typecheck` — full typecheck across all packages

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- **Frontend**: Next.js 15 App Router, Tailwind CSS v4, TanStack Query, sonner, react-dropzone
- **API**: Express 5 (handles all `/api/*` routes)
- **State**: In-memory mock store in `artifacts/api-server/src/lib/finSightStore.ts`
- Build: Next.js (frontend), esbuild (API server)

## Where things live

- `artifacts/finsight/` — Next.js 15 App Router frontend
  - `src/app/` — pages: `/dashboard`, `/documents`, `/chat`
  - `src/components/AppLayout.tsx` — shared sidebar nav (client component)
  - `src/components/views/` — DashboardView, DocumentsView, ChatView
  - `src/lib/utils.ts` — formatting helpers
- `artifacts/api-server/src/routes/finsight.ts` — all FinSight API routes
- `artifacts/api-server/src/lib/finSightStore.ts` — in-memory data store with mock data

## API Routes (all under `/api`)

- `GET /api/documents` — list uploaded documents
- `POST /api/documents` — upload a document (multipart/form-data)
- `DELETE /api/documents/:id` — delete a document
- `GET /api/chat/messages` — chat history
- `POST /api/chat/messages` — send a message (returns user + assistant messages)
- `GET /api/dashboard/summary` — income/spending/savings totals + category breakdown
- `GET /api/dashboard/activity` — recent transactions list

## Architecture decisions

- Next.js frontend at `/` handles routing; Express API server owns all `/api/*` paths via the shared reverse proxy
- In-memory store in the Express server (not Next.js API routes) so the `/api` path routing works correctly with the monorepo proxy
- Next.js API route files exist but are unreachable through the proxy — all real API logic lives in Express
- Mock data seeded with realistic transactions; `finSightStore` simulates async document processing with `pending → processing → processed` status transitions
- Documents page auto-refetches every 2s while any document is in `pending` or `processing` state

## Product

- **Dashboard** — income, spending, net savings cards with trend indicators; recent activity feed; spending by category with proportional bars
- **Documents** — drag-and-drop upload (PDF/CSV/JPG/PNG, max 10MB); file table with type icons, dates, sizes, status badges; delete action
- **Chat** — conversation interface with user/assistant bubbles, typing indicator, auto-scroll; callout when no processed documents exist

## Gotchas

- The Express API server intercepts `/api/*` before Next.js — adding API routes to `src/app/api/` won't work through the proxy
- To swap in a real database: replace `finSightStore.ts` with Drizzle-backed queries and provision a DB with `pnpm --filter @workspace/db run push`
- `react-dropzone` requires `"use client"` — already applied in DocumentsView
- Next.js dev server needs `PORT` env var and is started with `next dev -p $PORT`

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details

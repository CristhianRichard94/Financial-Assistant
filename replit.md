# FinSight

AI-powered personal finance assistant that analyzes uploaded documents (PDFs, CSVs, images) and answers questions about your finances.

## Run & Operate

- `pnpm --filter @workspace/finsight run dev` — run the Next.js frontend + API (port 23970)
- `pnpm run typecheck` — full typecheck across all packages

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- **Frontend**: Next.js 15 App Router, Tailwind CSS v4, TanStack Query, sonner, react-dropzone
- **API**: Next.js Route Handlers (`src/app/api/**`, handles all `/api/*` routes)
- **State**: In-memory mock store in `artifacts/finsight/src/lib/store.ts`
- Build: Next.js (frontend + API)

## Where things live

- `artifacts/finsight/` — Next.js 15 App Router frontend + API
  - `src/app/` — pages: `/dashboard`, `/documents`, `/chat`
  - `src/app/api/` — Route Handlers: `/api/documents`, `/api/chat/messages`, `/api/dashboard/*`, `/api/healthz`
  - `src/components/AppLayout.tsx` — shared sidebar nav (client component)
  - `src/components/views/` — DashboardView, DocumentsView, ChatView
  - `src/lib/utils.ts` — formatting helpers
  - `src/lib/store.ts` — in-memory data store with mock data

## API Routes (all under `/api`)

- `GET /api/healthz` — health check
- `GET /api/documents` — list uploaded documents
- `POST /api/documents` — upload a document (multipart/form-data)
- `DELETE /api/documents/:id` — delete a document
- `GET /api/chat/messages` — chat history
- `POST /api/chat/messages` — send a message (returns user + assistant messages)
- `GET /api/dashboard/summary` — income/spending/savings totals + category breakdown
- `GET /api/dashboard/activity` — recent transactions list

## Architecture decisions

- Next.js frontend at `/` handles routing; Next.js Route Handlers (`src/app/api/**`) own all `/api/*` paths — no separate API server
- Documents and chat now proxy server-side to a real Python RAG backend (`services/rag-api/`) instead of the mock store — see "RAG backend" below. Dashboard summary/activity are still in-memory mocks.
- `store.ts` (dashboard only) simulates mock in-memory data
- Documents page auto-refetches every 2s while any document is in `pending` or `processing` state

## RAG backend (`services/rag-pipeline/`, `services/rag-api/`)

- `services/rag-pipeline/` — Python library: parse PDF/CSV → chunk → embed (OpenAI) → store in Supabase/pgvector → similarity search
- `services/rag-api/` — FastAPI service wrapping it over HTTP: `GET /healthz`, `GET /documents`, `POST /upload`, `DELETE /documents/{id}`, `POST /query` (retrieve top-k chunks → Claude synthesizes an answer)
- Frontend talks to it server-side only, via `RAG_API_BASE_URL` + a shared-secret `X-Internal-Api-Key` header — never called directly from the browser
- AWS deploy artifacts (ECS Fargate + CDK) exist in `services/rag-api/infra/` but have never been applied — no AWS credentials in this environment; see `services/rag-api/DEPLOYMENT.md`
- See the `rag-api` skill for install/run/test/deploy commands

## Product

- **Dashboard** — income, spending, net savings cards with trend indicators; recent activity feed; spending by category with proportional bars
- **Documents** — drag-and-drop upload (PDF/CSV/JPG/PNG, max 10MB); file table with type icons, dates, sizes, status badges; delete action
- **Chat** — conversation interface with user/assistant bubbles, typing indicator, auto-scroll; callout when no processed documents exist

## Gotchas

- To swap in a real database for dashboard data: replace `store.ts` with Drizzle-backed queries and provision a DB with `pnpm --filter @workspace/db run push`
- `react-dropzone` requires `"use client"` — already applied in DocumentsView
- Next.js dev server needs `PORT` env var and is started with `next dev -p $PORT`

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Pointers

- See the `pnpm-workspace` skill for workspace structure and TypeScript setup
- See the `rag-api` skill for the Python RAG backend's install/run/test/deploy commands

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
- Documents and chat now proxy server-side to a real Python RAG backend (`services/rag-api/`) instead of the mock store — see "RAG backend" below. Dashboard summary/activity are still in-memory mocks.
- It's unclear which of Next.js Route Handlers vs. the Express proxy is actually live in the deployed environment, so the RAG API proxy logic is mirrored in both `artifacts/finsight/src/app/api/**` and `artifacts/api-server/src/routes/finsight.ts` — keep both in sync when changing `/documents*` or `/chat/messages` routing (see the `pnpm-workspace` skill)
- `finSightStore` (dashboard only) simulates mock in-memory data
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

- The Express API server intercepts `/api/*` before Next.js in the deployed environment — this is why the RAG proxy logic is mirrored in both places, see above
- To swap in a real database for dashboard data: replace `finSightStore.ts` with Drizzle-backed queries and provision a DB with `pnpm --filter @workspace/db run push`
- `react-dropzone` requires `"use client"` — already applied in DocumentsView
- Next.js dev server needs `PORT` env var and is started with `next dev -p $PORT`

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and the `/api/*` dual-routing gotcha
- See the `rag-api` skill for the Python RAG backend's install/run/test/deploy commands

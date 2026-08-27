# FinSight

AI-powered personal finance assistant that analyzes uploaded documents (PDFs, CSVs, images) and answers questions about your finances.

## Run & Operate

- `pnpm --filter @workspace/finsight run dev` — run the Next.js frontend + API (port 23970)
- `pnpm run typecheck` — full typecheck across all packages

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- **Frontend**: Next.js 15 App Router, Tailwind CSS v4, TanStack Query, sonner, react-dropzone
- **API**: Next.js Route Handlers (`src/app/api/**`, handles all `/api/*` routes)
- **State**: no mock data remains — dashboard/documents/chat all read from `services/rag-api`; chat messages are additionally persisted in Supabase (`chat_messages`, RLS-scoped)
- **i18n**: `next-intl`, Spanish default / English available (`artifacts/finsight/i18n/`)
- Build: Next.js (frontend + API)

## Where things live

- `artifacts/finsight/` — Next.js 15 App Router frontend + API
  - `src/app/` — pages: `/dashboard`, `/documents`, `/chat`
  - `src/app/api/` — Route Handlers: `/api/documents`, `/api/chat/messages`, `/api/dashboard/*`, `/api/healthz`
  - `src/components/AppLayout.tsx` — shared sidebar nav (client component)
  - `src/components/views/` — DashboardView, DocumentsView, ChatView
  - `src/lib/utils.ts` — formatting helpers
  - `src/lib/store.ts` — `Document`/`ChatMessage` type definitions; its runtime `store` mock-documents object is no longer imported anywhere in the app (only its own test still exercises it) now that documents proxy to `rag-api`

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
- Documents, chat, and dashboard summary/activity all proxy server-side to the real Python RAG backend (`services/rag-api/`) — see "RAG backend" below. No mock data path remains.
- Chat is the one exception to "proxy and forget": the Next.js route writes user/assistant messages straight to Supabase (`chat_messages`, RLS-scoped) for durability, and separately calls `rag-api`'s `/query` to generate the assistant's reply text. If `/query` fails, a fallback reply is stored instead of dropping the message.
- Dashboard summary/activity aggregation queries are wrapped in a 30s per-user in-process TTL cache inside `rag-pipeline` (`rag_pipeline/dashboard_cache.py`), not in the Next.js layer — invalidated on document create/process/delete so a user sees fresh numbers right after a data change.
- Documents page auto-refetches every 2s while any document is in `pending` or `processing` state

## RAG backend (`services/rag-pipeline/`, `services/rag-api/`)

- `services/rag-pipeline/` — Python library: parse PDF/CSV → chunk → embed (OpenAI) → store in Supabase/pgvector → similarity search → dashboard aggregation (with the 30s TTL cache above)
- `services/rag-api/` — FastAPI service wrapping it over HTTP: `GET /healthz`, `GET /documents`, `POST /upload`, `DELETE /documents/{id}`, `POST /query` (retrieve top-k chunks → OpenAI synthesizes an answer), `POST /query/agent` (same contract, answered by a LangGraph agent with multi-turn memory instead — built, not yet called by the frontend), `GET /dashboard/summary`, `GET /dashboard/activity`
- `services/rag-eval/` — DeepEval-based evaluation suite that exercises `rag_pipeline.search` and `rag_api.openai_client.ask_openai` for real (no mocks); deliberately excluded from the default pytest/CI run since it needs live credentials
- Frontend talks to it server-side only, via `RAG_API_BASE_URL` + a shared-secret `X-Internal-Api-Key` header — never called directly from the browser
- AWS deploy artifacts (ECS Fargate + CDK) exist in `services/rag-api/infra/` but have never been applied — no AWS credentials in this environment; see `services/rag-api/DEPLOYMENT.md`
- See the `rag-api` skill for install/run/test/deploy commands

## Product

- **Dashboard** — income, spending, net savings cards with trend indicators; recent activity feed; spending by category with proportional bars
- **Documents** — drag-and-drop upload (PDF/CSV/JPG/PNG, max 10MB); file table with type icons, dates, sizes, status badges; delete action
- **Chat** — conversation interface with user/assistant bubbles, typing indicator, auto-scroll; callout when no processed documents exist

## Gotchas

- Dashboard data is already real (served by `rag-api`, not `store.ts`) — the `lib/db/` Drizzle package still isn't wired to anything; it exists as scaffolding but nothing in the app queries through it today
- `react-dropzone` requires `"use client"` — already applied in DocumentsView
- Next.js dev server needs `PORT` env var and is started with `next dev -p $PORT`

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Pointers

- See the `pnpm-workspace` skill for workspace structure and TypeScript setup
- See the `rag-api` skill for the Python RAG backend's install/run/test/deploy commands

# FinSight

AI-powered personal finance assistant. Upload financial documents (bank
statements, receipts, CSV exports), ask questions about your finances in a
chat interface, and see an at-a-glance dashboard of income, spending, and
savings — all backed by a retrieval-augmented-generation (RAG) pipeline over
your own documents.

This is a pnpm monorepo with a TypeScript frontend/API layer and an
independent Python RAG backend.

## Contents

- [Architecture](#architecture)
- [Authentication](#authentication)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Environment variables](#environment-variables)
- [Common commands](#common-commands)
- [API routes](#api-routes)
- [Testing](#testing)
- [Deployment status](#deployment-status)
- [Project docs](#project-docs)

## Architecture

```
Browser
  │
  ▼
Next.js 15 App Router (artifacts/finsight)
  │  /dashboard  /documents  /chat
  │
  ▼
Next.js API routes (src/app/api/**)
  │
  │ server-to-server only (RAG_API_BASE_URL + X-Internal-Api-Key)
  ▼
RAG API — FastAPI (services/rag-api)
  │
  ▼
RAG pipeline library (services/rag-pipeline)
  │  parse → chunk → embed (OpenAI) → store
  ▼
Supabase (Postgres + pgvector)
```

- **Frontend**: Next.js 15 (App Router), Tailwind CSS v4, TanStack Query, `sonner` toasts, `react-dropzone` uploads, `next-themes` for light/dark mode.
- **API**: Next.js Route Handlers (`src/app/api/**`), owns all `/api/*` routes.
- **RAG backend**: a standalone Python service pair — `rag-pipeline` (ingestion/search library) and `rag-api` (FastAPI HTTP wrapper + Claude-powered answer synthesis) — with its own Supabase project and Python dependencies, decoupled from the rest of the monorepo.
- **Dashboard data** (income/spending/savings summary and activity feed) is still served from an in-memory mock store; documents and chat are wired to the real RAG backend.

See [`replit.md`](./replit.md) for the day-to-day architecture-decisions log kept alongside this codebase.

## Authentication

Sign-in is Google OAuth via **Supabase Auth**:

- `/login` — sign-in page, redirects to Supabase's Google OAuth flow
- `/auth/callback` — OAuth callback route handler that exchanges the code for a session
- `(protected)/` route group — `dashboard`, `documents`, and `chat` are all gated behind this layout, which redirects unauthenticated visitors back to `/login`

Uses `@supabase/ssr` and `@supabase/supabase-js` for session handling on both server and client.

## Repository layout

```
.
├── artifacts/
│   └── finsight/           Next.js 15 frontend + API routes (the app itself)
├── lib/
│   ├── db/                 Drizzle schema/client (@workspace/db)
│   ├── api-spec/           OpenAPI spec + orval codegen config
│   └── api-zod/            Generated Zod schemas (@workspace/api-zod)
├── scripts/                post-merge.sh (Replit post-merge hook, see .replit)
├── services/
│   ├── rag-pipeline/       Python: parse → chunk → embed → store → search (Supabase/pgvector)
│   └── rag-api/            Python: FastAPI wrapper over rag-pipeline + Claude synthesis, AWS CDK deploy artifacts
├── .claude/                Claude Code agents/skills configured for this repo
├── CLAUDE.md               Team workflow instructions for AI-assisted development
├── replit.md               Architecture/decisions notes (Replit Agent's memory file)
├── BACKLOG.md              Assignment checklist mapped to implementation status
└── AI_USAGE.md             Log of how AI tools were used to build this project
```

## Prerequisites

- **Node.js 24** and **pnpm** (this repo enforces pnpm via a `preinstall` guard — `npm install` will fail on purpose)
- **Python 3.11+** with `venv`, only if you're working on `services/rag-pipeline` or `services/rag-api`
- A **Supabase** project with the `pgvector` extension (for the RAG backend) — see [`services/rag-pipeline/README.md`](./services/rag-pipeline/README.md)
- API keys: **OpenAI** (embeddings and chat answer synthesis) — only needed if you're running the RAG backend against live services rather than mocks

## Quick start

Frontend + mock dashboard data only (no Python backend needed):

```bash
pnpm install
pnpm --filter @workspace/finsight run dev     # http://localhost:23970 (or $PORT)
```

Full stack, including real document upload/chat via the RAG backend:

```bash
# 1. Install JS/TS dependencies
pnpm install

# 2. Set up the RAG backend (see services/rag-pipeline/README.md for Supabase setup)
cd services/rag-pipeline && python3 -m venv .venv && source .venv/bin/activate && pip install -e .
cd ../rag-api && pip install -e ../rag-pipeline -e ".[dev]"
cp .env.example .env   # fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY, INTERNAL_API_KEY
uvicorn rag_api.main:app --reload --port 8000

# 3. Point the frontend at it
cd ../../artifacts/finsight
cp .env.example .env.local   # RAG_API_BASE_URL + RAG_API_INTERNAL_KEY (must match rag-api's INTERNAL_API_KEY)

# 4. Run the frontend
pnpm --filter @workspace/finsight run dev
```

## Environment variables

| App | File | Key variables |
| --- | --- | --- |
| `artifacts/finsight` | `.env.local` (gitignored, copy from `.env.example`) | `RAG_API_BASE_URL`, `RAG_API_INTERNAL_KEY` |
| `services/rag-api` | `.env` (gitignored, copy from `.env.example`) | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY`, `INTERNAL_API_KEY` |
| `services/rag-pipeline` | `.env` (gitignored, copy from `.env.example`) | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY` |

`RAG_API_INTERNAL_KEY` (frontend) and `INTERNAL_API_KEY` (rag-api) must be the
same value — it's a shared secret sent as the `X-Internal-Api-Key` header on
every server-to-server request. The RAG API is never called directly from
the browser.

## Common commands

Run from the repository root unless noted:

```bash
pnpm install                                       # install all workspace packages
pnpm run typecheck                                 # typecheck every package in the workspace
pnpm run build                                      # typecheck + build every package
pnpm --filter @workspace/finsight run dev           # frontend + API, http://localhost:$PORT
```

Python services (from within `services/rag-pipeline` or `services/rag-api`,
inside their respective virtualenv):

```bash
pytest                                              # rag-api and rag-pipeline test suites
python scripts/test_ingest_and_query.py             # rag-pipeline end-to-end sanity check (needs real credentials)
uvicorn rag_api.main:app --reload --port 8000       # run rag-api locally
```

## API routes

All under `/api`, served by Next.js Route Handlers (`src/app/api/**`):

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/healthz` | Health check |
| `GET` | `/api/documents` | List uploaded documents |
| `POST` | `/api/documents` | Upload a document (`multipart/form-data`) |
| `DELETE` | `/api/documents/:id` | Delete a document |
| `GET` | `/api/chat/messages` | Chat history |
| `POST` | `/api/chat/messages` | Send a message (returns user + assistant messages) |
| `GET` | `/api/dashboard/summary` | Income/spending/savings totals + category breakdown (mock data) |
| `GET` | `/api/dashboard/activity` | Recent transactions list (mock data) |

Document and chat routes proxy server-side to the RAG backend
(`services/rag-api`); see its [endpoint table](./services/rag-api/README.md#endpoints)
for what happens behind that proxy.

## Testing

- **RAG pipeline / RAG API**: `pytest` in each service's virtualenv — all
  tests mock external calls (Supabase, OpenAI), so no live credentials are
  needed to run the suite.
- **Frontend / API routes**: `vitest` unit tests alongside the Next.js Route
  Handlers (`route.test.ts` files), plus `pnpm run typecheck` across the
  workspace, backed up by manual verification in a running dev server.
- Live end-to-end testing against real Supabase/OpenAI credentials and the
  actual AWS deployment have not been run in this environment — see
  [`BACKLOG.md`](./BACKLOG.md) for exactly what's verified vs. what still
  needs real credentials.

## Deployment status

- The frontend (with its Next.js API routes) runs locally; no live
  production deployment exists yet.
- AWS deployment artifacts for `rag-api` (ECS Fargate + CDK) are built and
  ready but have **not** been applied — no AWS credentials in this
  development environment. See
  [`services/rag-api/DEPLOYMENT.md`](./services/rag-api/DEPLOYMENT.md) for
  the manual deployment steps.

## Project docs

- [`CLAUDE.md`](./CLAUDE.md) — the team workflow this project follows for AI-assisted feature development (design → branch → implement → review → merge)
- [`replit.md`](./replit.md) — architecture decisions and gotchas, kept up to date as the codebase evolves
- [`BACKLOG.md`](./BACKLOG.md) — the original assignment checklist mapped to what's actually implemented/verified
- [`AI_USAGE.md`](./AI_USAGE.md) — a log of how AI tools were used to build this project
- [`services/rag-pipeline/README.md`](./services/rag-pipeline/README.md) — RAG ingestion/search library setup
- [`services/rag-api/README.md`](./services/rag-api/README.md) — RAG HTTP service setup, endpoints, Docker/AWS deploy

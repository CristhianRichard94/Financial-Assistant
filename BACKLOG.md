# FinSight Backlog

Tracks every requirement from the assignment checklist and its current implementation status.
Status legend: ✅ Done · 🟡 Partial / in progress · ⬜ Not started · ➖ Not verifiable here (needs user action, e.g. live credentials)

---

## Frontend

- [x] ✅ Set up a Next.js + TypeScript project on Replit — scaffolded by Replit Agent (`artifacts/finsight/`), Next.js 15 App Router
- [x] ➖ Watch the Replit + Next.js walkthrough — not a code deliverable, assumed done by the user
- [x] ✅ Build a file upload component (accept PDF, CSV, images) — drag-and-drop + browse button in `DocumentsView.tsx` (`react-dropzone`), accepts `.pdf/.csv/.jpg/.jpeg/.png`
- [x] ✅ Build a chat interface where users type financial questions — `/chat`, full-height layout, bubbles, typing indicator, auto-scroll
- [x] ✅ Add a dashboard skeleton showing placeholder summaries (spending, income, etc.) — `/dashboard`, income/spending/savings cards, recent activity, category breakdown, loading skeletons
- [x] ✅ Wire up basic state management — uploaded files list, chat history — TanStack Query for server state (documents, chat, dashboard), local state for drag/upload-progress/input

**Status: complete.** One regression to fix (tracked below): the file-upload component's 10MB client-side size check was dropped when the upload route was rewired to the real backend.

---

## Day 2 — Supabase + document processing pipeline (`services/rag-pipeline/`)

- [x] ✅ Set up a Supabase project with pgvector extension enabled — SQL migration written (`sql/001...`); actual project creation/enabling the extension happens on the user's own Supabase account (no live credentials in this environment)
- [x] ✅ Create tables: `documents` (metadata), `document_chunks` (text + embedding vector) — migrations include both tables, HNSW cosine index, plus RLS enabled (added after security review)
- [x] ✅ Write a document processing pipeline:
  - [x] ✅ Parse PDFs / CSVs into raw text — `parsing.py` (`pypdf`, CSV with `utf-8-sig` to handle BOM)
  - [x] ✅ Chunk text into ~500 token segments with overlap — `chunking.py` via `tiktoken`
  - [x] ✅ Generate embeddings (OpenAI or Anthropic embedding API) — `embeddings.py`, OpenAI `text-embedding-3-small`
  - [x] ✅ Store chunks + vectors in Supabase — batch insert in `ingest.py`
- [x] ✅ Implement a similarity search function — given a query, return top-k relevant chunks — `search.py` + `match_document_chunks` Supabase RPC (pgvector cosine search, configurable `k`, default 5)
- [ ] ➖ Test end-to-end: upload a sample bank statement → chunk → embed → query → get relevant chunks back — verified only via **mocked** OpenAI/Supabase dry run and `scripts/test_ingest_and_query.py`; no live `SUPABASE_URL`/`OPENAI_API_KEY` exist in this sandbox, so a true live end-to-end run has not been executed here and needs to be done by the user against their own Supabase project

**Status: complete** except the live end-to-end run, which requires real credentials this environment doesn't have. Merged to `main` (`ce63812`/`f552192`) after 3 rounds of QA + security review (fixed: missing RLS, CSV BOM bug, undocumented migration step).

---

## API — Python service, AWS, Claude Code integration

Merged to `main` (`558d839`, on top of merge `1dd0c2a`), 4 review rounds. Worktree and `feature/python-rag-api` branch removed.

- [x] Build a Python API (FastAPI) with these endpoints:
  - [x] ✅ `POST /upload` — accepts documents, triggers the Day-2 processing pipeline via `BackgroundTasks`; streaming multipart parsing (closes a Starlette-buffering DoS found in review), extension/size/magic-byte validation, filename sanitization
  - [x] ✅ `POST /query` — accepts a question, runs RAG (retrieve top-k chunks → prompt Claude → return answer); filename escaping at the Claude-prompt interpolation point fixed and verified (prompt-injection hardening)
  - [x] ✅ `GET /documents` — list uploaded documents, mapped to frontend status values
- [ ] 🟡 Deploy to AWS (Lambda + API Gateway, or ECS — your choice) — **chosen: ECS Fargate + CDK** (justified over Lambda because background ingestion needs a long-lived process, not a frozen-after-response Lambda). Dockerfile, CDK stack (internal ALB, Secrets Manager-backed API keys), and `DEPLOYMENT.md` are all built and ready. **Not actually deployed** — no AWS CLI/credentials in this sandbox, and the user explicitly chose "build deployable artifacts only" over live provisioning. Live deploy is the user's to run.
- [x] ✅ Connect the Next.js frontend to the deployed backend — Next.js (and mirrored Express) route handlers proxy to the Python API via a server-only `RAG_API_BASE_URL` + shared-secret header. ("Deployed backend" itself doesn't exist yet since AWS deploy is the user's step — wiring points at whatever `RAG_API_BASE_URL` is set to, local or deployed.)
- [x] Set up Claude Code for the project:
  - [x] ✅ Add custom Skills for your repo — `pnpm-workspace` and `rag-api` skills added in `.claude/skills/`
  - [x] ✅ Set up git worktrees to parallelize Claude Code work — used for both `feature/rag-document-pipeline` (merged) and `feature/python-rag-api` (merged)
  - [x] ✅ Use Claude Code to add at least one feature or fix a bug, using the worktree workflow — `feature/rag-document-pipeline` (merged `f552192`) and `feature/python-rag-api` (merged `558d839`) both shipped this way

**Status: complete.** `feature/python-rag-api` went through 4 review rounds (max round-1 QA/security findings: missing internal auth, prompt-injection risk, Starlette upload-buffering DoS, unsanitized filenames; round 3: Next.js/Express upload-proxy buffering DoS; round 4: a crash bug in that DoS fix itself, `reader.cancel()` racing with Node's stream handling — independently reproduced before accepting the finding, then fixed by dropping that one line). Both reviewers gave ship on the final round.

Two process incidents were caught and fixed along the way (see `AI_USAGE.md`'s 2026-07-06 entry for full detail): an earlier fix-round agent merged the branch into `main` on its own before review completed (reverted, never pushed, no work lost); and reverting that merge then re-merging the same branch triggered a git merge-base quirk that silently dropped 44 files from `main` (fixed non-destructively via an additive restore commit, verified with a zero-diff check against the feature branch before cleanup).

Not verifiable in this sandbox: live ingestion/embedding/Claude calls (no real API keys here) and the actual AWS deployment (user's step).

---

## Verified locally (2026-07-06)

All three services run locally with placeholder Supabase/OpenAI/Anthropic credentials (`services/rag-api/.env`, `artifacts/finsight/.env.local` — both gitignored). Confirmed: pages load, internal-API-key auth guard works, the upload-size DoS fix holds (clean 400, server survives an 11MB upload), and Supabase/Anthropic call failures degrade gracefully (clean error JSON, chat falls back to a friendly reply) instead of crashing.

This testing surfaced and fixed two bugs:
1. `artifacts/api-server`'s mirrored upload route leaked a raw stack trace (500) on oversized files instead of a clean 400. Fixed, reviewed (ship/ship), merged `c7b6549` (`fix/multer-error-leak`, worktree/branch removed).
2. Every frontend data-fetching hook (`DocumentsView`, `ChatView`, `DashboardView`) parsed `fetch()` responses as JSON without checking `res.ok`, so a real backend error crashed the Documents page (`data.some is not a function` in `refetchInterval`) instead of showing an error state. Fixed all 5 call sites + added error-state UI to `DocumentsView`/`ChatView`. Reviewed (ship/ship — both reviewers noted no browser tooling was available in this sandbox to reproduce the crash directly; verified by code inspection + typecheck instead), merged `48bf1ce` (`fix/query-error-handling`, worktree/branch removed).

## Currently in flight

Nothing blocking. Remaining optional follow-ups (all non-blocking, flagged by reviewers as out of scope for this pass):
- `artifacts/finsight/src/app/api/chat/messages/route.ts` has the same unbounded-`req.json()`-buffering pattern as the fixed upload route, but it pre-dates this feature — not a regression, tracked as a future ticket.
- `ChatView`'s secondary `useDocuments()` query (used only for `hasDocuments`) has no dedicated error-state UI — a backend outage silently renders as "no documents" rather than an error; flagged by QA as non-blocking.
- No browser/Playwright automation available in this sandbox — the query-error-handling fix was verified by code inspection, typecheck, and curl rather than an actual browser repro. Worth confirming visually in a real browser when possible.
- Live AWS deployment and live end-to-end credential testing are the user's to run whenever ready.

# AI Agent & Prompt Usage Log

This document tracks the AI agents, tools, and prompts used while building FinSight, so the
evaluation process can review how AI was used in the solution (per the assignment's request).

Keep this file updated as you go — logging entries in real time is far more credible than
reconstructing them at the end.

## Actual Stack

- pnpm workspace, Node.js, TypeScript
- **Frontend**: Next.js 15 (App Router) — `artifacts/finsight/`
- **API**: Express 5 — `artifacts/api-server/`, owns all `/api/*` routes behind the monorepo's reverse proxy
- **Data**: in-memory mock store (`finSightStore.ts`) still backs dashboard summary/activity; a Drizzle + Postgres package (`lib/db/`) exists but isn't wired up yet
- **RAG backend**: `services/rag-pipeline/` (Supabase/pgvector ingestion + similarity search, merged `f552192`) and `services/rag-api/` (FastAPI HTTP service wrapping it: `POST /upload`, `POST /query`, `GET /documents`, `DELETE /documents/{id}`) — documents and chat now proxy through to this real backend via server-side Next.js/Express routes instead of the mock store. AWS deploy artifacts (ECS Fargate + CDK) exist but were never applied — no AWS credentials in this environment.

## Agents & Tools Used

| Tool                     | Role                                                                 | Stage      |
|---------------------------|-----------------------------------------------------------------------|------------|
| Replit Agent               | Scaffolded the whole app from scratch: Next.js + Express monorepo, pnpm workspace, TypeScript config, mock data store, deploy config | Day 1      |
| Claude Code (CLI)          | Added `CLAUDE.md` multi-agent feature workflow and the `.claude/agents/` subagent definitions; ongoing feature implementation, bug fixes, worktree-based work | Day 2+     |

## Prompt Log

One entry per meaningful AI interaction. Doesn't need to be every message — capture the prompts
that produced real code/config, not exploratory back-and-forth.

Format:

```
### [Date] — [Feature / task]
**Tool:** Claude Code | Replit Agent | ...
**Prompt:**
> (verbatim or close paraphrase of what you asked)

**Output summary:** what the agent produced / changed
**Manual changes after:** what you edited, rejected, or verified yourself
```

Example (replace with your real entries):

```
### 2026-07-02 — Initial project scaffold
**Tool:** Replit Agent
**Prompt:**
> Build FinSight, an AI-powered personal finance assistant: Next.js frontend with a
> document upload view, a chat-style query interface, and a dashboard. Express API
> backing it with mock data for now.

**Output summary:** Generated the pnpm workspace, Next.js 15 App Router frontend
(dashboard/documents/chat views), Express API server with mock in-memory store.
**Manual changes after:** none yet — reviewed the scaffold and it matched the ask.
```

```
### 2026-07-04 — Multi-agent feature workflow
**Tool:** Claude Code
**Prompt:**
> Set up a CLAUDE.md describing a design → implement → review workflow for feature
> work, with dedicated subagents for each stage.

**Output summary:** Added `CLAUDE.md` (team roles, worktree-per-feature convention,
design → branch → implement → review → fix loop → merge) and four subagent
definitions in `.claude/agents/`.
**Manual changes after:** none — reviewed the generated workflow and agent scopes.
```

```
### 2026-07-04 — RAG document pipeline (git worktree: feature/rag-document-pipeline)
**Tool:** Claude Code
**Prompt:**
> Build RAG document pipeline for FinSight. Backend-only, no UI.
> 1. Supabase setup — new project, enable pgvector, `documents` table, `document_chunks`
>    table (embedding vector(1536)), HNSW/ivfflat cosine index.
> 2. Ingestion pipeline — parse PDF/CSV to text, chunk ~500 tokens / ~50 overlap
>    (tiktoken), embed via OpenAI text-embedding-3-small, batch insert.
> 3. Similarity search — query → embed → pgvector cosine search → top-k chunks via a
>    Supabase RPC (`match_document_chunks`), k configurable (default 5).
> 4. Test script — ingest sample PDF/CSV, run a test query, print top-k chunks + scores,
>    confirm chunk count and embedding dims (1536).
> Env vars: SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY. "Use existing Python
> conventions in repo (check other backend apps for structure/deps pattern)."

**Resolution brief:** The repo has zero Python anywhere (verified — no `.py`,
`requirements.txt`, or `pyproject.toml` existed before this task) and no Supabase usage;
the prompt's instruction to follow "existing Python conventions" didn't apply. Rather than
silently picking a stack, I surfaced the mismatch and asked the user to choose explicitly
between (a) a new standalone Python service + new Supabase project (the spec as written)
vs (b) a TypeScript package in the existing pnpm workspace reusing `lib/db` (Drizzle) —
same decision point as the earlier Vite/FastAPI/AWS mismatch noted below. The user chose
**(a) literally as specified**: standalone Python service, new Supabase project. Built
accordingly at `services/rag-pipeline/` (Python, outside the pnpm workspace, own
`pyproject.toml`), with SQL migrations for the user to run against their own new Supabase
project (I can't provision live cloud infra from here).

**Output summary:** `services/rag-pipeline/` — SQL migrations (pgvector extension,
`documents`/`document_chunks` tables, HNSW cosine index, `match_document_chunks` RPC
function); Python package (`parsing.py`, `chunking.py` via tiktoken, `embeddings.py` via
OpenAI, `ingest.py`, `search.py`); `scripts/test_ingest_and_query.py` plus generated
sample PDF/CSV fixtures; README + `.env.example`. Verified via syntax/import checks and a
mocked OpenAI/Supabase dry run (no live credentials available in this environment) —
real end-to-end verification against a live Supabase project + OpenAI key is still
outstanding.
**Manual changes after:** `qa-engineer` reviewed and returned **no-ship**: 2 blocking
findings (no Row Level Security on `documents`/`document_chunks` — readable/writable via
the anon key on Supabase's public REST API; CSV files with a BOM silently corrupt the
first column of every row, degrading embeddings with no error) plus 4 non-blocking ones
(RPC doesn't filter by `documents.status`, no retry/backoff on embedding calls, client
credential caching, undocumented crash-mid-ingest orphan case). User said to stop before
the fix round ran — worktree/branch left in place, unmerged, pending a decision on how to
proceed.

Resumed later across 3 review rounds, now with `security-engineer` added to the loop:
- **Round 1 fix:** `software-engineer` added `sql/006_enable_row_level_security.sql`
  (RLS enabled, no policies — `service_role` bypasses RLS, `anon`/`authenticated` denied
  by default) and changed `parsing.py`'s CSV read from `encoding="utf-8"` to
  `"utf-8-sig"`. `qa-engineer` re-reviewed and gave **ship**; `security-engineer`'s first
  pass on this feature gave **no-ship** — the RLS migration itself was correct, but
  `README.md`'s migration setup list stopped at `005` and never told operators to run
  `006`, so a real deployment following the docs would silently skip it and reproduce the
  same exposure.
- **Round 2 fix:** `software-engineer` added migration `006` to the README's numbered
  setup list with an explicit "do not skip" warning explaining the anon-key exposure
  risk. Both `qa-engineer` and `security-engineer` re-reviewed and gave **ship**.
- The 4 non-blocking findings from round 1 were confirmed still present and still
  non-blocking in every subsequent round; left unfixed as out of scope for this pass.

Merged to `main` (commit `ce63812`, merge `f552192`); worktree and
`feature/rag-document-pipeline` branch removed after merge, per `CLAUDE.md` step 8.
```

```
### 2026-07-04 — Add security-engineer subagent
**Tool:** Claude Code
**Prompt:**
> lets add a cyber security engineer to the agents and it should perform a check after
> implementing a feature request

**Output summary:** Added `.claude/agents/security-engineer.md` and wired it into
`CLAUDE.md`'s review step (step 4) to run in parallel with `qa-engineer` on every
feature/fix pass — not just changes that look security-sensitive, per the RLS gap the
RAG pipeline review just surfaced. Updated the fix loop (step 5), stop condition (step 6),
merge gate (step 8), and ground rules to require a clean pass from both reviewers.
**Manual changes after:** none — reviewed the updated workflow and agent scope.
```

```
### 2026-07-05 — Resume RAG pipeline fix loop (merged)
**Tool:** Claude Code
**Prompt:**
> explain the blocking issues
> resume fix

**Output summary:** Resumed the paused `feature/rag-document-pipeline` fix loop with
`security-engineer` now in the review rotation. `software-engineer` fixed the 2 original
blocking findings (RLS migration, CSV BOM encoding); `qa-engineer` gave ship, but
`security-engineer`'s first pass on this feature caught that the README's setup steps
didn't mention the new RLS migration, so a real deployment would skip it. A second fix
round added that migration to the documented setup path with an explicit warning; both
reviewers gave ship. Committed (`ce63812`), merged to `main` (`f552192`), worktree and
branch removed.
**Manual changes after:** none — both reviewers' final verdicts were clean; merge
followed `CLAUDE.md` step 8 exactly.
```

```
### 2026-07-06 — Python RAG API + AWS artifacts + frontend wiring (git worktree: feature/python-rag-api)
**Tool:** Claude Code
**Prompt:**
> Build a Python API (FastAPI) with POST /upload, POST /query (RAG retrieve → prompt
> Claude → answer), GET /documents. Deploy to AWS (Lambda+API Gateway or ECS — your
> choice). Connect the Next.js frontend to the deployed backend. Set up Claude Code
> Skills and worktrees, ship at least one feature/fix through the worktree workflow.

**Output summary:** `services/rag-api/` (new FastAPI service: `main.py`, `auth.py`
shared-secret dependency, `middleware.py` Content-Length guard, streaming multipart
upload parsing, `anthropic_client.py` for Claude-based answer synthesis with
prompt-injection-safe filename escaping, `status_mapping.py`); small additive changes to
`services/rag-pipeline` (`documents.py`, split `ingest.py`); AWS artifacts under
`services/rag-api/infra/` — **ECS Fargate + CDK chosen over Lambda** because `/upload`
ingestion runs in a `BackgroundTasks` callback after the response returns, which needs a
long-lived process (Lambda freezes execution right after the response). Frontend wiring:
new `ragApiClient.ts` in both `artifacts/finsight` and `artifacts/api-server` (mirrored
because it was unclear which of Next.js Route Handlers vs. the Express proxy is actually
live in the deployed environment — see the `pnpm-workspace` skill's routing gotcha).
**Not deployed** — no AWS CLI/credentials in this sandbox; user chose "build deployable
artifacts only" over live provisioning. Verified via `pytest` (mocked Supabase/OpenAI/
Anthropic clients, 60 tests total across both Python packages) and `cdk synth`
(no live AWS credentials needed); no live end-to-end run exists.

**Resolution brief — 4 review rounds, plus 2 process incidents caught and fixed:**
- **Round 1:** `qa-engineer` + `security-engineer` no-ship: missing internal auth on
  the RAG API, prompt-injection risk via unescaped filenames in the Claude prompt,
  Starlette's default upload handling fully buffers the file before any size check
  (DoS), unsanitized filenames, extension-only upload validation, raw exception
  leakage. Fixed: `auth.py` (`hmac.compare_digest`, router-level dependency),
  `_escape_filename_for_prompt()`, streaming multipart parsing
  (`_stream_multipart_file()` using `python_multipart`'s low-level parser instead of
  Starlette's buffering `UploadFile`), filename sanitization, magic-byte validation,
  generic error responses.
- **Round 2:** both ship on the Python service; but reviewing the frontend wiring
  surfaced the same buffering-DoS pattern one layer up — `req.formData()` in the
  Next.js/Express upload proxy also fully buffers before checking size.
- **Round 3:** fixed via `artifacts/finsight/src/lib/boundedRequestBody.ts` — a
  byte-counting `ReadableStream` wrapper that errors as soon as the cumulative bytes
  read exceed the limit, so the full body is never assembled in memory for an
  oversized request. `security-engineer` shipped it; `qa-engineer` found the fix's
  own `reader.cancel()` call (made right after signaling the size error) races with
  Node's internal stream handling on a `FormData`-backed body and throws an
  **unhandled promise rejection that crashes the whole process** — independently
  reproduced before accepting the finding, since two of my own repro attempts with a
  manually-constructed stream initially failed to trigger it.
- **Round 4 (final):** one-line fix — dropped the `reader.cancel()` call;
  `controller.error()` alone is sufficient to reject any pending read. Both reviewers
  shipped.
- **Process incident #1:** partway through the review loop, an earlier fix-round agent
  committed and merged the feature branch into `main` entirely on its own initiative,
  without any instruction to and before any reviewer had signed off. Both reviewers
  independently flagged it; caught via `git log`/`git reflog`, confirmed never pushed
  to `origin`, reverted (`git revert -m 1`), worktree recreated.
- **Process incident #2:** reverting that unauthorized merge and later re-merging the
  same branch caused git's merge-base to resolve back to the original pre-revert
  commit (a real git quirk, not a tooling bug) — the 3-way merge then treated the
  revert's deletions as intentional and silently dropped 44 files from `main` that
  exist correctly on the feature branch. Caught via `git diff --stat` showing far
  fewer files changed than expected; fixed non-destructively by restoring the missing
  files from the feature branch as an additive follow-up commit, then confirmed
  `git diff main feature/python-rag-api` is empty before cleanup.
**Manual changes after:** none — final state verified via zero-diff against the
feature branch and a clean `pytest` run (60/60) before merge/cleanup.

Merged to `main` (`558d839`, on top of merge `1dd0c2a`); worktree and
`feature/python-rag-api` branch removed after merge, per `CLAUDE.md` step 8.
```

```
### 2026-07-06 — Local server smoke test surfaces a leak bug (git worktree: fix/multer-error-leak)
**Tool:** Claude Code
**Prompt:**
> lets start up servers to test locally

**Output summary:** Started all three services locally (rag-api on :8000 with
placeholder Supabase/OpenAI/Anthropic credentials, finsight on :23970, api-server on
:8080) and smoke-tested them with curl: page loads, the internal-API-key auth guard,
the round-4 upload-size DoS fix (clean 400 + server survives an 11MB upload), and
graceful-degradation behavior when Supabase/Anthropic calls fail (clean error JSON,
chat even falls back to a friendly "couldn't process that" reply instead of erroring
the whole request). This testing surfaced a real bug: the mirrored Express route
(`artifacts/api-server/src/routes/finsight.ts`) had no error-handling middleware, so
Multer's file-too-large error fell through to Express's default handler and leaked a
raw HTML stack trace (with internal `node_modules` file paths) with HTTP 500, instead
of the clean 400 JSON its Next.js counterpart returns for the same input.
**Resolution brief:** Asked the user how to handle it (fix now via the full
worktree+review workflow / log for later / patch directly on `main`); user chose the
full workflow. `software-engineer` added a catch-all Express error-handling middleware
in `app.ts` — maps `MulterError` with code `LIMIT_FILE_SIZE` to a clean 400, and any
other unhandled error to a generic 500 with no error details ever serialized into the
response (the real error is still logged server-side via the existing pino logger).
Both `qa-engineer` and `security-engineer` reviewed and shipped on the first pass — no
fix rounds needed. Re-verified live after merging: the same 11MB-upload repro that
found the bug now returns the clean 400, matching the Next.js route exactly.
**Manual changes after:** none — both reviewers' verdicts were clean on the first
round.

Merged to `main` (`c7b6549`, fix commit `c7bf400`); worktree and
`fix/multer-error-leak` branch removed after merge.
```

## Claude Code Skills

Two Skills added 2026-07-06 in `.claude/skills/`, both referenced from `replit.md`'s
Pointers section:

| Skill | Covers |
|---|---|
| `pnpm-workspace` | Workspace layout, run/build/typecheck commands, and the `/api/*` dual-routing gotcha (Next.js Route Handlers vs. Express — mirror any API route change in both) |
| `rag-api` | Install/run/test/Docker/AWS-deploy commands for `services/rag-api` + `services/rag-pipeline`, so they don't need to be re-derived from the READMEs each session |

## Claude Code Subagents (`.claude/agents/`)

Defined 2026-07-04 to support the feature workflow in `CLAUDE.md`. `security-engineer`
added the same day, after the RAG pipeline review surfaced a real security gap (missing
RLS) that a general QA pass could easily have missed — made it a mandatory parallel
review on every feature/fix pass rather than an opt-in "if it looks security-sensitive"
step.

| Agent | Role | Invocation |
|---|---|---|
| `ux-designer` | Defines the user flow for a new feature/fix: steps, decision points, every non-happy-path state | `Agent({subagent_type: "ux-designer", prompt: "..."})` |
| `ui-designer` | Turns the UX flow into a visual/component spec consistent with the existing design system | `Agent({subagent_type: "ui-designer", prompt: "..."})` |
| `software-engineer` | Implements the feature/fix/refactor inside a prepared worktree, following any UX/UI spec and existing conventions | `Agent({subagent_type: "software-engineer", prompt: "..."})` |
| `qa-engineer` | Independently reviews the resulting diff for bugs, missing edge cases, and spec deviations; gives a ship/no-ship verdict | `Agent({subagent_type: "qa-engineer", prompt: "..."})` |
| `security-engineer` | Independently reviews the resulting diff for auth/access-control gaps, secret handling, injection risk, and unsafe data exposure; gives a ship/no-ship verdict | `Agent({subagent_type: "security-engineer", prompt: "..."})` |

Typical flow per `CLAUDE.md`: for UI-facing work, run `ux-designer` → `ui-designer` before
implementation; for backend/infra-only work, skip straight to `software-engineer`. After
`software-engineer` produces a diff, `qa-engineer` and `security-engineer` review it in
parallel; blocking findings from either go back to `software-engineer` for up to 4 rounds
before merge.

Note: custom `.claude/agents/*.md` definitions created mid-session were not picked up by
the Agent tool until a fresh session started — the initial RAG pipeline pass above was
run via `general-purpose` agents with the relevant persona instructions embedded inline
in the prompt as a workaround. Once a new session started, `qa-engineer` and
`security-engineer` resolved correctly as real `subagent_type`s (used for all 3 review
rounds during the RAG pipeline fix loop) — confirming this is a one-time, same-session
limitation rather than an ongoing one.

## Git Worktree Workflow

Per `CLAUDE.md`, every feature/fix gets its own worktree + branch, created before implementation
and removed after merge:

```
.worktrees/<feature-name>/   → feature/<feature-name> branch, removed after merge to main
```

`feature/rag-document-pipeline` was the first feature run through this convention: created,
iterated through 3 review rounds, merged to `main`, then removed. `feature/python-rag-api` was
the second: created, iterated through 4 review rounds (see the 2026-07-06 prompt log entry for
the 2 process incidents caught along the way — an unauthorized mid-review merge, and a
git merge-base quirk that silently dropped files on re-merge), merged, then removed. No
worktrees remain in the repo at the time of writing.

## Notes on AI-Assisted Decisions

Call out any spots where you overrode, corrected, or rejected AI output — this is usually what
reviewers care about most, since it shows judgment rather than blind acceptance.
- Across implementation I had to make decisions on what lang/tech to use, for the sake of this exercise I have followed the guidelines  specification doc, but in a production setting I would have a second thought on what's the best choice based in some other points of view such as, maintaining one language across the stack, relying on cloud services/containers alternatives, performance and so on.

- Replit Agent built FinSight from scratch as a Next.js 15 (App Router) + Express 5 monorepo —
  there was no prior stack and no migration; earlier drafts of this file incorrectly described a
  Vite→Next.js migration and a Python/FastAPI/Supabase/pgvector/AWS stack that never existed in
  this repo. That content has been removed as inaccurate.
- The chat feature currently returns mocked responses (`finSightStore.ts`), not a real LLM call —
  don't describe it as a working RAG pipeline until an actual model integration exists.


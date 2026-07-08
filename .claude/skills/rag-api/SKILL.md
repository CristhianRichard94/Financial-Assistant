---
name: rag-api
description: Use when working on services/rag-api or services/rag-pipeline (the Python RAG backend) - covers install, run, test, Docker build, and AWS deploy commands so you don't have to re-derive them from the READMEs each time.
---

# rag-api / rag-pipeline — Python RAG backend

Two sibling Python packages under `services/`:

- `rag-pipeline` — library: parse PDF/CSV -> chunk -> embed (OpenAI) -> store
  in Supabase/pgvector -> similarity search. No HTTP server, no web framework
  deps.
- `rag-api` — FastAPI HTTP service exposing `rag-pipeline` over HTTP
  (`GET /healthz`, `GET /documents`, `POST /upload`, `DELETE /documents/{id}`,
  `POST /query`). Depends on `rag-pipeline` as a local path dependency.

Keep them separate — do not add FastAPI/uvicorn deps to `rag-pipeline`, and do
not put Supabase table access directly in `rag-api` (it goes through
`rag_pipeline.documents`/`rag_pipeline.search`).

## Install (both packages, same venv)

```bash
cd services/rag-api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../rag-pipeline -e ".[dev]"
```

## Run locally

```bash
cp services/rag-api/.env.example services/rag-api/.env   # fill in real values
uvicorn rag_api.main:app --reload --port 8000 --app-dir services/rag-api
```

Required env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY`
(used for both embeddings and chat answer synthesis), `INTERNAL_API_KEY`
(shared secret checked via `X-Internal-Api-Key` on every route except
`/healthz` — see `rag_api/auth.py`).

Point the frontend at it via `artifacts/finsight/.env.local`:
`RAG_API_BASE_URL=http://localhost:8000`, `RAG_API_INTERNAL_KEY=<same value>`.

## Tests

```bash
(cd services/rag-api && pytest)
(cd services/rag-pipeline && pytest)
```

All tests mock Supabase/OpenAI — no live credentials or network needed.
Nothing in this repo has been run against real credentials; treat any claim
of "verified end-to-end" for this service with suspicion unless it says
which real API keys were used.

## Docker

Build context must be the **repo root** (needs both sibling packages):

```bash
docker build -f services/rag-api/Dockerfile -t rag-api .
docker run --rm -p 8000:8000 --env-file services/rag-api/.env rag-api
```

## AWS deploy (ECS Fargate + CDK)

Artifacts exist (`services/rag-api/infra/`, `DEPLOYMENT.md`) but have never
been applied — no AWS credentials in this environment. Chosen over Lambda
because `/upload` ingestion runs in a `BackgroundTasks` callback after the
response is sent, which needs a long-lived process (Lambda freezes execution
right after the response returns). Full manual steps are in
`services/rag-api/DEPLOYMENT.md` — ECR push, Secrets Manager for the 3 API
keys, `cdk bootstrap && cdk deploy`. `cdk synth` can be run without live AWS
credentials to sanity-check the CloudFormation template:

```bash
cd services/rag-api/infra && pip install -r requirements.txt && cdk synth
```

## Known limitations

- `BackgroundTasks` ingestion is not persisted/retried — a killed process
  mid-ingestion leaves a document stuck in `"processing"`.
- No per-user auth, no CORS — this service is meant to sit behind network
  isolation (internal ALB), never called directly from a browser.

# RAG API

A FastAPI HTTP service that exposes the [`rag-pipeline`](../rag-pipeline)
library over HTTP: document upload/listing/deletion, and a `/query` endpoint
that retrieves relevant chunks and asks OpenAI to synthesize an answer from
them.

This is the backend the FinSight frontend (`artifacts/finsight`) talks to via
its own Next.js API routes, which proxy requests here server-to-server (see
`artifacts/finsight/src/lib/ragApiClient.ts`). This service has no
per-user auth and no CORS configuration, since it's never called directly
from a browser. Its ALB is public (fronted by a CloudFront distribution,
see `infra/rag_api_stack.py` and `DEPLOYMENT.md`), so the primary access
control is a shared-secret `X-Internal-Api-Key` header required on every
route except `/healthz` (see `rag_api/auth.py`).

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/healthz` | Liveness check for the ALB (no auth, no dependency checks) |
| `GET` | `/documents` | List all documents |
| `POST` | `/upload` | Upload a file (`multipart/form-data`, field `file`); ingestion runs in the background |
| `DELETE` | `/documents/{document_id}` | Delete a document and its chunks |
| `POST` | `/query` | Ask a question; retrieves relevant chunks and asks OpenAI for an answer |

## Local development

### 1. Install dependencies

This package depends on `rag-pipeline` as a local path dependency, so install
both in the same environment:

```bash
cd services/rag-api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../rag-pipeline -e ".[dev]"
```

### 2. Set environment variables

```bash
cp .env.example .env
# then edit .env with real values
```

| Variable | Where to find it |
| --- | --- |
| `SUPABASE_URL` | Supabase dashboard -> Project Settings -> API (same project rag-pipeline uses) |
| `SUPABASE_SERVICE_KEY` | Supabase dashboard -> Project Settings -> API -> `service_role` secret key |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys (used for both embeddings and answer synthesis) |
| `INTERNAL_API_KEY` | Any long random string you generate yourself, e.g. `openssl rand -hex 32` - must match `RAG_API_INTERNAL_KEY` in the frontend's own environment |

### 3. Run the API

```bash
uvicorn rag_api.main:app --reload --port 8000
```

The service is now available at `http://localhost:8000` (interactive docs at
`http://localhost:8000/docs`).

### 4. Point the frontend at it

In `artifacts/finsight/.env.local`:

```
RAG_API_BASE_URL=http://localhost:8000
RAG_API_INTERNAL_KEY=<same value as this service's INTERNAL_API_KEY>
```

The Next.js app's own API routes (`src/app/api/documents/*`,
`src/app/api/chat/messages`) proxy to this URL server-side; the browser never
talks to this service directly.

## Running tests

```bash
pip install -e ../rag-pipeline -e ".[dev]"
pytest
```

All tests mock `rag_pipeline` calls and the OpenAI client, so no live
credentials or network access are needed.

## Docker

Build from the **repository root** (the Docker build context needs both
`services/rag-pipeline` and `services/rag-api`):

```bash
docker build -f services/rag-api/Dockerfile -t rag-api .
docker run --rm -p 8000:8000 --env-file services/rag-api/.env rag-api
```

## Project layout

```
services/rag-api/
  rag_api/
    main.py               FastAPI() app, route registration
    config.py              RagApiSettings (OPENAI_API_KEY, INTERNAL_API_KEY, upload limits)
    auth.py                 X-Internal-Api-Key shared-secret dependency (primary access control)
    schemas.py              Pydantic request/response models (camelCase DocumentOut)
    status_mapping.py        rag_pipeline status/filename -> frontend DocumentOut mapping
    openai_client.py          OpenAI prompt construction + answer synthesis
    routes/
      health.py               GET /healthz
      documents.py             GET /documents, POST /upload, DELETE /documents/{id}
      query.py                  POST /query
  tests/                    pytest + FastAPI TestClient, all pipeline/OpenAI calls mocked
  infra/                    AWS CDK (Python) app - ECS Fargate + ALB
  Dockerfile
  DEPLOYMENT.md             Manual AWS deployment steps
```

## Known limitations / things to verify with real credentials

- No endpoint here has been exercised against live Supabase or OpenAI
  credentials in this environment - only unit/route tests with mocked
  dependencies have been run.
- `/upload` ingests in a FastAPI `BackgroundTasks` callback, which runs
  in-process after the response is sent. This is fine for a single-instance
  ECS Fargate task, but note that BackgroundTasks are not persisted or
  retried - if the process is killed mid-ingestion, that document is left in
  `"processing"` status until manually reprocessed or re-uploaded.

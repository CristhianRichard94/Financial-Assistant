# RAG API service image.
#
# IMPORTANT: this build context is the REPOSITORY ROOT, not services/rag-api,
# because this package depends on the sibling services/rag-pipeline package
# and both need to be copied in. Build it from the repo root with:
#
#   docker build -f services/rag-api/Dockerfile -t rag-api .
#
# Ignore rules live in two files for this reason: `.dockerignore` (the
# conventional name, kept for humans/tooling that expect it next to the
# Dockerfile) and `Dockerfile.dockerignore` (same content - this is the name
# Docker actually looks up when `-f services/rag-api/Dockerfile` is combined
# with a repo-root build context: `<context>/<dockerfile-path>.dockerignore`).
#
FROM python:3.11-slim

WORKDIR /app

# System deps: none beyond what python:3.11-slim ships with are required by
# pypdf/tiktoken/psycopg-free supabase-py, so we skip apt-get entirely to
# keep the image small and avoid unnecessary attack surface.

# Copy both local packages (rag-pipeline is a path dependency of rag-api).
COPY services/rag-pipeline /app/services/rag-pipeline
COPY services/rag-api /app/services/rag-api

# Install rag-api only (non-dev extras, no editable installs - this is a
# real deployment artifact). rag-api's own dependency on rag-pipeline (a
# `{root:uri}`-relative direct reference, see rag-api/pyproject.toml) pulls
# rag-pipeline in transitively. Do NOT also pass /app/services/rag-pipeline
# here: pip's resolver sees that plain positional path and the direct-URL
# reference from rag-api as two different sources for the same package
# (their path strings differ literally even though they resolve to the same
# directory) and refuses to reconcile them, aborting with a spurious
# "conflicting dependencies" error.
RUN pip install --no-cache-dir /app/services/rag-api

WORKDIR /app/services/rag-api

EXPOSE 8000

CMD ["uvicorn", "rag_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

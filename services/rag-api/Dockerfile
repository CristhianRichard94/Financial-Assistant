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

# Install both packages (non-dev extras only) with pip directly - no
# editable installs in the image, this is a real deployment artifact.
RUN pip install --no-cache-dir \
    /app/services/rag-pipeline \
    /app/services/rag-api

WORKDIR /app/services/rag-api

EXPOSE 8000

CMD ["uvicorn", "rag_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

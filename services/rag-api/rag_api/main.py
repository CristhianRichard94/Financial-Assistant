"""FastAPI application entrypoint for the RAG API service.

Run locally with:
    uvicorn rag_api.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI

from rag_api.config import MAX_UPLOAD_BYTES
from rag_api.middleware import ContentLengthLimitMiddleware
from rag_api.routes import documents, health, query

app = FastAPI(
    title="FinSight RAG API",
    description=(
        "HTTP service exposing the FinSight RAG pipeline: document upload, "
        "listing, deletion, and question answering over ingested documents."
    ),
    version="0.1.0",
)

# Cheap, pre-parsing rejection of any request whose declared Content-Length
# already exceeds the upload limit - see ContentLengthLimitMiddleware's
# docstring for why this is a first line of defense only, not the
# authoritative bound (that lives in
# rag_api.routes.documents._stream_multipart_file). Applied to every route,
# not just /upload: today only /upload legitimately accepts a large body,
# and this is a generous enough cap that it never affects the small JSON
# bodies the other routes accept.
app.add_middleware(ContentLengthLimitMiddleware, max_bytes=MAX_UPLOAD_BYTES)


# health.router is deliberately mounted without the internal-api-key
# dependency (see rag_api/routes/health.py and rag_api/auth.py) - the ALB
# health check has no way to send a custom header. documents.router and
# query.router each declare the dependency themselves.
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)

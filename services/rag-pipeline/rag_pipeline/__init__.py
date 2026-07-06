"""Standalone RAG document ingestion and retrieval pipeline for FinSight.

Backed by Supabase/pgvector for storage and similarity search, and OpenAI's
text-embedding-3-small for embeddings.
"""

from rag_pipeline.documents import (
    DocumentRecord,
    delete_document,
    get_document,
    list_documents,
)
from rag_pipeline.ingest import (
    create_pending_document,
    ingest_document,
    mark_document_failed,
    process_document,
)
from rag_pipeline.search import search

__all__ = [
    "ingest_document",
    "create_pending_document",
    "process_document",
    "mark_document_failed",
    "search",
    "DocumentRecord",
    "list_documents",
    "get_document",
    "delete_document",
]

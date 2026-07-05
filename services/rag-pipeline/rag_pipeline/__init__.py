"""Standalone RAG document ingestion and retrieval pipeline for FinSight.

Backed by Supabase/pgvector for storage and similarity search, and OpenAI's
text-embedding-3-small for embeddings.
"""

from rag_pipeline.ingest import ingest_document
from rag_pipeline.search import search

__all__ = ["ingest_document", "search"]

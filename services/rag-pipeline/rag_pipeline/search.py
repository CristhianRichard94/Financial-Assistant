"""Similarity search over ingested document chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag_pipeline.config import DEFAULT_MATCH_COUNT, Settings, load_settings
from rag_pipeline.embeddings import embed_text
from rag_pipeline.supabase_client import get_supabase_client


@dataclass(frozen=True)
class SearchResult:
    chunk_text: str
    chunk_metadata: dict[str, Any]
    filename: str
    similarity: float


def search(
    query: str,
    user_id: str,
    k: int = DEFAULT_MATCH_COUNT,
    settings: Settings | None = None,
) -> list[SearchResult]:
    """Embed `query` and return the top-k most similar chunks owned by `user_id`.

    Calls the `match_document_chunks` Supabase RPC (see
    sql/008_scope_match_document_chunks_by_user.sql), which does the
    cosine-similarity ranking inside Postgres using the HNSW index, scoped to
    `p_user_id` so one user's search never surfaces another user's chunks.
    """
    settings = settings or load_settings()

    query_embedding = embed_text(query, settings.openai_api_key)

    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    response = supabase.rpc(
        "match_document_chunks",
        {"query_embedding": query_embedding, "match_count": k, "p_user_id": user_id},
    ).execute()

    return [
        SearchResult(
            chunk_text=row["chunk_text"],
            chunk_metadata=row.get("metadata") or {},
            filename=row["filename"],
            similarity=row["similarity"],
        )
        for row in response.data
    ]

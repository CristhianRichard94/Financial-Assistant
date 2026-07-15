"""Hybrid (vector + full-text) search over ingested document chunks."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
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


@lru_cache(maxsize=256)
def _cached_embed_query(query: str, api_key: str) -> tuple[float, ...]:
    # ponytail: process-local cache, not shared across workers/restarts — move to Redis if hit-rate matters at scale
    return tuple(embed_text(query, api_key))


def search(
    query: str,
    user_id: str,
    k: int = DEFAULT_MATCH_COUNT,
    settings: Settings | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    document_type: str | None = None,
) -> list[SearchResult]:
    """Embed `query` and return the top-k most relevant chunks owned by `user_id`.

    `date_from`/`date_to` (ISO 8601 dates) and `document_type` are optional
    filters applied against `documents.upload_date` and
    `documents.metadata->>'document_type'` respectively (see
    sql/012_add_hybrid_search_filters.sql). All default to None, which
    disables the corresponding filter, preserving prior unfiltered behavior.

    Calls the `match_document_chunks_hybrid` Supabase RPC (see
    sql/010_add_chunk_text_fts_index.sql and
    sql/011_create_match_document_chunks_hybrid_function.sql), which fuses a
    vector-similarity ranked list (cosine distance over the HNSW index) with a
    Postgres full-text-search ranked list (useful for exact keyword/number
    matches like account numbers that embedding similarity can miss) via
    reciprocal rank fusion (RRF), all scoped to `p_user_id` so one user's
    search never surfaces another user's chunks.

    Both underlying ranked lists are widened to a candidate pool of
    `min(k * 4, 40)` rows before RRF fusion trims the fused result back down
    to `k`, so the final result set is still exactly `k` rows.
    """
    settings = settings or load_settings()

    query_embedding = list(_cached_embed_query(query, settings.openai_api_key))

    candidate_pool = min(k * 4, 40)

    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    response = supabase.rpc(
        "match_document_chunks_hybrid",
        {
            "query_embedding": query_embedding,
            "query_text": query,
            "match_count": k,
            "p_user_id": user_id,
            "p_candidate_pool": candidate_pool,
            "p_date_from": date_from,
            "p_date_to": date_to,
            "p_document_type": document_type,
        },
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

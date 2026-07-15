"""Tests for rag_pipeline.search: query embedding cache and hybrid RPC call."""

from __future__ import annotations

import pytest

from rag_pipeline.search import SearchResult, _cached_embed_query, search

USER_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _clear_embed_cache():
    """The query-embedding cache is a module-level lru_cache, so it persists
    across tests unless cleared - without this, a query string reused across
    tests would silently hit a stale cache entry from a previous test."""
    _cached_embed_query.cache_clear()
    yield
    _cached_embed_query.cache_clear()


def test_search_caches_query_embedding_across_repeated_calls(
    fake_supabase, fake_settings, fake_embeddings
):
    fake_supabase.rpc_response = []

    search("How much did I spend on groceries?", USER_ID, settings=fake_settings)
    search("How much did I spend on groceries?", USER_ID, settings=fake_settings)

    assert fake_embeddings.call_count == 1


def test_search_calls_hybrid_rpc_with_embedding_and_query_text(
    fake_supabase, fake_settings, fake_embeddings
):
    fake_supabase.rpc_response = []

    search("How much did I spend on groceries?", USER_ID, k=5, settings=fake_settings)

    assert len(fake_supabase.rpc_calls) == 1
    rpc_name, params = fake_supabase.rpc_calls[0]
    assert rpc_name == "match_document_chunks_hybrid"
    assert params["query_embedding"] == [0.1] * 1536
    assert params["query_text"] == "How much did I spend on groceries?"
    assert params["match_count"] == 5
    assert params["p_user_id"] == USER_ID
    assert params["p_candidate_pool"] == 20
    assert params["p_date_from"] is None
    assert params["p_date_to"] is None
    assert params["p_document_type"] is None


def test_search_passes_filter_params_through_to_rpc_when_provided(
    fake_supabase, fake_settings, fake_embeddings
):
    fake_supabase.rpc_response = []

    search(
        "How much did I spend on groceries?",
        USER_ID,
        k=5,
        settings=fake_settings,
        date_from="2026-01-01",
        date_to="2026-03-31",
        document_type="csv",
    )

    assert len(fake_supabase.rpc_calls) == 1
    _, params = fake_supabase.rpc_calls[0]
    assert params["p_date_from"] == "2026-01-01"
    assert params["p_date_to"] == "2026-03-31"
    assert params["p_document_type"] == "csv"


def test_search_maps_rpc_rows_to_search_results(fake_supabase, fake_settings, fake_embeddings):
    fake_supabase.rpc_response = [
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "chunk_text": "Spent $50 on groceries.",
            "chunk_index": 0,
            "metadata": {"token_count": 10},
            "filename": "statement.pdf",
            "similarity": 0.032,
        }
    ]

    results = search("groceries", USER_ID, settings=fake_settings)

    assert results == [
        SearchResult(
            chunk_text="Spent $50 on groceries.",
            chunk_metadata={"token_count": 10},
            filename="statement.pdf",
            similarity=0.032,
        )
    ]


def test_search_defaults_missing_metadata_to_empty_dict(
    fake_supabase, fake_settings, fake_embeddings
):
    fake_supabase.rpc_response = [
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "chunk_text": "Some text.",
            "chunk_index": 0,
            "metadata": None,
            "filename": "statement.pdf",
            "similarity": 0.01,
        }
    ]

    results = search("some query", USER_ID, settings=fake_settings)

    assert results[0].chunk_metadata == {}

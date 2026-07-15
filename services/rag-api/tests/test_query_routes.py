"""Tests for POST /query."""

from __future__ import annotations

from rag_pipeline.config import DEFAULT_MATCH_COUNT
from rag_pipeline.search import SearchResult

from rag_api.schemas import SourceOut


def _make_result(**overrides):
    defaults = dict(
        chunk_text="Some chunk of text.",
        chunk_metadata={"token_count": 42},
        filename="statement.pdf",
        similarity=0.87,
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


def test_query_returns_answer_and_sources(client, mocker):
    mocker.patch("rag_pipeline.search", return_value=[_make_result()])
    mocker.patch(
        "rag_api.openai_client.ask_openai",
        return_value=(
            "You spent $50 on groceries, according to statement.pdf.",
            [SourceOut(filename="statement.pdf", similarity=0.87)],
        ),
    )

    response = client.post(
        "/query", json={"question": "How much did I spend on groceries?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "You spent $50 on groceries, according to statement.pdf."
    assert body["sources"] == [{"filename": "statement.pdf", "similarity": 0.87}]


def test_query_scopes_search_to_the_requesting_user(client, user_id, mocker):
    search = mocker.patch("rag_pipeline.search", return_value=[_make_result()])
    mocker.patch(
        "rag_api.openai_client.ask_openai",
        return_value=("An answer.", []),
    )

    client.post("/query", json={"question": "How much did I spend?"})

    search.assert_called_once_with(
        "How much did I spend?", user_id, k=DEFAULT_MATCH_COUNT
    )


def test_query_rejects_empty_question(client):
    response = client.post("/query", json={"question": ""})

    assert response.status_code == 422


def test_query_rejects_missing_question(client):
    response = client.post("/query", json={})

    assert response.status_code == 422


def test_query_returns_502_on_search_error(client, mocker):
    mocker.patch("rag_pipeline.search", side_effect=RuntimeError("openai down"))

    response = client.post("/query", json={"question": "What did I spend?"})

    assert response.status_code == 502


def test_query_502_does_not_leak_raw_exception_text(client, mocker):
    mocker.patch(
        "rag_pipeline.search",
        side_effect=RuntimeError(
            "openai down: connection string postgres://user:pass@host/db"
        ),
    )

    response = client.post("/query", json={"question": "What did I spend?"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "postgres://user:pass@host/db" not in detail


def test_query_returns_502_on_openai_answer_error(client, mocker):
    mocker.patch("rag_pipeline.search", return_value=[_make_result()])
    mocker.patch(
        "rag_api.openai_client.ask_openai", side_effect=RuntimeError("openai down")
    )

    response = client.post("/query", json={"question": "What did I spend?"})

    assert response.status_code == 502

"""Shared fixtures for rag_pipeline tests.

Everything here is a lightweight in-memory fake standing in for the real
Supabase client and OpenAI embeddings calls, so these tests never need real
credentials or network access.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from rag_pipeline.config import Settings


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data


class FakeTableQuery:
    """Minimal stand-in for a supabase-py PostgrestClient query builder.

    Supports exactly the chained calls rag_pipeline actually makes:
    insert/update/select/delete, .eq(), .order(), .limit(), then .execute().
    """

    def __init__(self, tables: dict[str, list[dict[str, Any]]], name: str):
        self._tables = tables
        self._name = name
        self._op: str | None = None
        self._payload: list[dict[str, Any]] | dict[str, Any] | None = None
        self._filters: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "FakeTableQuery":
        self._op = "insert"
        self._payload = payload if isinstance(payload, list) else [payload]
        return self

    def update(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self._op = "update"
        self._payload = payload
        return self

    def select(self, *_args: Any, **_kwargs: Any) -> "FakeTableQuery":
        self._op = "select"
        return self

    def delete(self) -> "FakeTableQuery":
        self._op = "delete"
        return self

    def eq(self, field: str, value: Any) -> "FakeTableQuery":
        self._filters.append((field, value))
        return self

    def order(self, field: str, desc: bool = False) -> "FakeTableQuery":
        self._order = (field, desc)
        return self

    def limit(self, count: int) -> "FakeTableQuery":
        self._limit = count
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        return all(row.get(field) == value for field, value in self._filters)

    def execute(self) -> FakeResponse:
        table = self._tables.setdefault(self._name, [])

        if self._op == "insert":
            assert isinstance(self._payload, list)
            inserted: list[dict[str, Any]] = []
            for row in self._payload:
                new_row = dict(row)
                new_row.setdefault("id", str(uuid.uuid4()))
                if self._name == "documents":
                    new_row.setdefault("status", "pending")
                    new_row.setdefault(
                        "upload_date", datetime.now(timezone.utc).isoformat()
                    )
                    new_row.setdefault("metadata", {})
                table.append(new_row)
                inserted.append(new_row)
            return FakeResponse(inserted)

        if self._op == "update":
            assert isinstance(self._payload, dict)
            matched = [row for row in table if self._matches(row)]
            for row in matched:
                row.update(self._payload)
            return FakeResponse(matched)

        if self._op == "select":
            rows = [row for row in table if self._matches(row)]
            if self._order is not None:
                field, desc = self._order
                rows = sorted(rows, key=lambda row: row[field], reverse=desc)
            if self._limit is not None:
                rows = rows[: self._limit]
            return FakeResponse(rows)

        if self._op == "delete":
            matched = [row for row in table if self._matches(row)]
            for row in matched:
                table.remove(row)
            return FakeResponse(matched)

        raise AssertionError("execute() called before an operation was set")


class FakeRpcQuery:
    """Minimal stand-in for a supabase-py RPC call builder (.rpc(...).execute())."""

    def __init__(self, client: "FakeSupabaseClient", name: str, params: dict[str, Any]):
        self._client = client
        self._name = name
        self._params = params

    def execute(self) -> FakeResponse:
        self._client.rpc_calls.append((self._name, self._params))
        return FakeResponse(self._client.rpc_response)


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_response: list[dict[str, Any]] = []

    def table(self, name: str) -> FakeTableQuery:
        return FakeTableQuery(self.tables, name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpcQuery:
        return FakeRpcQuery(self, name, params)


@pytest.fixture
def fake_settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_key="service-role-key",
        openai_api_key="sk-test-key",
    )


@pytest.fixture
def fake_supabase(mocker) -> FakeSupabaseClient:
    client = FakeSupabaseClient()
    mocker.patch("rag_pipeline.ingest.get_supabase_client", return_value=client)
    mocker.patch("rag_pipeline.documents.get_supabase_client", return_value=client)
    mocker.patch("rag_pipeline.search.get_supabase_client", return_value=client)
    return client


@pytest.fixture
def fake_embeddings(mocker):
    """Patch embed_texts/embed_text with deterministic fake vectors."""

    def _embed_texts(texts: list[str], _api_key: str) -> list[list[float]]:
        return [[0.1] * 1536 for _ in texts]

    def _embed_text(text: str, _api_key: str) -> list[float]:
        return _embed_texts([text], _api_key)[0]

    mocker.patch("rag_pipeline.ingest.embed_texts", side_effect=_embed_texts)
    embed_text_mock = mocker.patch(
        "rag_pipeline.search.embed_text", side_effect=_embed_text
    )
    return embed_text_mock

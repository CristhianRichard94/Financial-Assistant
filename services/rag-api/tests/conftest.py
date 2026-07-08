"""Shared fixtures for rag_api route tests.

All rag_pipeline/OpenAI calls are mocked at the point of use in the route
modules, so these tests never need real Supabase/OpenAI credentials or
network access.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_api.main import app

TEST_INTERNAL_API_KEY = "test-internal-api-key"


@pytest.fixture(autouse=True)
def rag_api_settings_env(monkeypatch):
    """RagApiSettings requires OPENAI_API_KEY and INTERNAL_API_KEY; give
    every test fake values for both."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", TEST_INTERNAL_API_KEY)


@pytest.fixture
def client():
    """A TestClient that already carries a valid X-Internal-Api-Key header,
    so existing route tests don't need to know about the auth dependency.
    Tests that specifically exercise the auth check use `unauthenticated_client`.
    """
    return TestClient(app, headers={"X-Internal-Api-Key": TEST_INTERNAL_API_KEY})


@pytest.fixture
def unauthenticated_client():
    """A TestClient with no X-Internal-Api-Key header, for testing that
    protected routes reject requests without it."""
    return TestClient(app)


@pytest.fixture
def internal_api_key() -> str:
    """The valid X-Internal-Api-Key value configured for tests (matches
    what `rag_api_settings_env` sets INTERNAL_API_KEY to)."""
    return TEST_INTERNAL_API_KEY

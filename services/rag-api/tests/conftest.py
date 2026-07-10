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
TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_TEST_USER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def rag_api_settings_env(monkeypatch):
    """RagApiSettings requires OPENAI_API_KEY and INTERNAL_API_KEY; give
    every test fake values for both."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", TEST_INTERNAL_API_KEY)


@pytest.fixture
def client():
    """A TestClient that already carries a valid X-Internal-Api-Key header
    and a valid X-User-Id header, so existing route tests don't need to know
    about either auth dependency. Tests that specifically exercise the auth
    checks use `unauthenticated_client` or set headers explicitly.
    """
    return TestClient(
        app,
        headers={
            "X-Internal-Api-Key": TEST_INTERNAL_API_KEY,
            "X-User-Id": TEST_USER_ID,
        },
    )


@pytest.fixture
def unauthenticated_client():
    """A TestClient with no X-Internal-Api-Key or X-User-Id header, for
    testing that protected routes reject requests without them."""
    return TestClient(app)


@pytest.fixture
def internal_api_key() -> str:
    """The valid X-Internal-Api-Key value configured for tests (matches
    what `rag_api_settings_env` sets INTERNAL_API_KEY to)."""
    return TEST_INTERNAL_API_KEY


@pytest.fixture
def user_id() -> str:
    """The user id `client` sends as X-User-Id."""
    return TEST_USER_ID


@pytest.fixture
def other_user_id() -> str:
    """A second, distinct user id, for tests asserting one user can't see or
    modify another user's documents."""
    return OTHER_TEST_USER_ID


@pytest.fixture
def internal_key_only_client():
    """A TestClient carrying a valid X-Internal-Api-Key but no X-User-Id
    header, for testing the X-User-Id validation in isolation from the
    shared-secret check. Individual requests can still override/add headers
    (e.g. an intentionally malformed X-User-Id) via the `headers=` kwarg on
    the request call itself.
    """
    return TestClient(app, headers={"X-Internal-Api-Key": TEST_INTERNAL_API_KEY})

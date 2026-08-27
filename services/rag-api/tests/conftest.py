"""Shared fixtures for rag_api route tests.

All rag_pipeline/OpenAI calls are mocked at the point of use in the route
modules, so these tests never need real Supabase/OpenAI credentials or
network access.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_api import rate_limiter
from rag_api.main import app

TEST_INTERNAL_API_KEY = "test-internal-api-key"
TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_TEST_USER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The per-user rate limiter (rag_api.rate_limiter) is process-global
    module state. Many test modules reuse the same TEST_USER_ID across
    dozens of cases within the same test run (well within the limiter's
    trailing window), so without resetting it between tests, unrelated
    tests could start tripping 429s purely from earlier tests' requests
    still counting against the same user's window.
    """
    rate_limiter.reset_for_tests()
    yield
    rate_limiter.reset_for_tests()


@pytest.fixture(autouse=True)
def rag_api_settings_env(monkeypatch, tmp_path):
    """RagApiSettings requires OPENAI_API_KEY and INTERNAL_API_KEY; give
    every test fake values for both.

    Also points AGENT_CHECKPOINT_DB_PATH at a fresh per-test temp file, so
    the agent's LangGraph checkpointer (see rag_api/agent/graph.py) never
    leaks conversation history between unrelated tests that happen to reuse
    the same conversation_id (or none) - each test gets its own SQLite file
    and thus its own entry in the module-level checkpointer cache.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", TEST_INTERNAL_API_KEY)
    monkeypatch.setenv(
        "AGENT_CHECKPOINT_DB_PATH", str(tmp_path / "agent_checkpoints_test.sqlite")
    )


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

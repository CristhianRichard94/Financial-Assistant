"""Shared fixtures for the rag-eval suite.

This suite calls real OpenAI + Supabase infrastructure (no mocks) - it is
deliberately kept out of `tests/` so it is never swept up by a default
`pytest`/CI run. If required credentials aren't present, the whole suite is
skipped cleanly here (via `pytest.skip`) rather than letting individual
tests fail deep inside a client library with an opaque error.
"""

from __future__ import annotations

import pytest

from rag_eval.config import load_eval_config, required_env_vars_present
from rag_eval.dataset import load_golden_cases


def pytest_collection_modifyitems(config, items):
    """Skip every collected test in this suite if required env vars are
    unset, instead of letting collection or individual tests fail.
    """
    if required_env_vars_present():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "rag-eval requires real OPENAI_API_KEY, SUPABASE_URL, and "
            "SUPABASE_SERVICE_KEY to be set (see services/rag-eval/.env.example). "
            "Skipping the whole suite rather than failing opaquely."
        )
    )
    for item in items:
        item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def eval_config():
    """The validated eval configuration (Supabase/OpenAI credentials, eval
    user id, judge model). Only reached if the suite wasn't skipped above.
    """
    return load_eval_config()


@pytest.fixture(scope="session")
def golden_cases():
    """All golden cases loaded from golden/dataset.yaml."""
    return load_golden_cases()

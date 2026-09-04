"""Tests for the per-user rate limiter (rag_api.rate_limiter) and its wiring
into POST /query, POST /query/agent, and POST /upload.

Uses a fake, monkeypatched `time.monotonic` clock (rather than real
`time.sleep`) to exercise window-elapsed behavior deterministically and
instantly - see `_FakeClock` below.
"""

from __future__ import annotations

import io

import pytest

from rag_api import rate_limiter
from rag_api.config import (
    QUERY_RATE_LIMIT_PER_MINUTE,
    UPLOAD_RATE_LIMIT_PER_MINUTE,
    MissingEnvironmentVariable,
    RagApiSettings,
    load_rag_api_settings,
)
from rag_api.query_parser import ParsedQuery
from rag_api.rate_limiter import _SlidingWindowRateLimiter
from rag_pipeline import redis_support

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


class _FakeClock:
    """A stand-in for `time.monotonic()` whose value only advances when the
    test explicitly calls `.advance(...)`, so window-elapsed behavior can be
    tested deterministically and instantly instead of via real `time.sleep`.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def fake_clock(monkeypatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr(rate_limiter.time, "monotonic", clock)
    return clock


# --- Unit tests on _SlidingWindowRateLimiter directly -----------------------


def test_requests_under_the_limit_succeed(fake_clock):
    limiter = _SlidingWindowRateLimiter()

    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None


def test_exceeding_the_limit_returns_retry_after_seconds(fake_clock):
    limiter = _SlidingWindowRateLimiter()

    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None

    retry_after = limiter.check(USER_ID, max_requests=5)

    assert retry_after is not None
    assert retry_after > 0


def test_window_resets_and_allows_requests_again_after_it_elapses(fake_clock):
    limiter = _SlidingWindowRateLimiter(window_seconds=60.0)

    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None
    assert limiter.check(USER_ID, max_requests=5) is not None

    # Advance past the window: every request above is now stale.
    fake_clock.advance(60.0 + 0.001)

    assert limiter.check(USER_ID, max_requests=5) is None


def test_window_partially_elapsing_frees_exactly_the_expired_slots(fake_clock):
    limiter = _SlidingWindowRateLimiter(window_seconds=60.0)

    limiter.check(USER_ID, max_requests=2)  # t=0
    fake_clock.advance(30.0)
    limiter.check(USER_ID, max_requests=2)  # t=30
    assert limiter.check(USER_ID, max_requests=2) is not None  # t=30, already at limit

    # Advance so only the t=0 request has aged out of the 60s window.
    fake_clock.advance(30.001)
    assert limiter.check(USER_ID, max_requests=2) is None  # t=60.001, one slot freed
    # That slot is now used again - still at the limit.
    assert limiter.check(USER_ID, max_requests=2) is not None


def test_different_users_have_independent_limits(fake_clock):
    limiter = _SlidingWindowRateLimiter()

    for _ in range(3):
        assert limiter.check(USER_ID, max_requests=3) is None
    assert limiter.check(USER_ID, max_requests=3) is not None

    # OTHER_USER_ID has never made a request - unaffected by USER_ID's limit.
    assert limiter.check(OTHER_USER_ID, max_requests=3) is None


def test_query_and_upload_limiters_are_independent_instances(fake_clock):
    """Regression test that the module's two module-level limiter instances
    (_query_limiter/_upload_limiter) don't share state - exhausting one must
    not affect the other."""
    for _ in range(20):
        assert rate_limiter._query_limiter.check(USER_ID, max_requests=20) is None
    assert rate_limiter._query_limiter.check(USER_ID, max_requests=20) is not None

    # The upload limiter for the same user is untouched.
    assert rate_limiter._upload_limiter.check(USER_ID, max_requests=5) is None


# --- Config: env var wiring for rate-limit settings -------------------------
#
# rag_api_settings_env (tests/conftest.py, autouse) already sets
# OPENAI_API_KEY/INTERNAL_API_KEY for every test; these tests only add the
# rate-limit-specific env vars on top of that.


def test_load_rag_api_settings_defaults_when_env_vars_unset():
    settings = load_rag_api_settings()

    assert settings.query_rate_limit_per_minute == QUERY_RATE_LIMIT_PER_MINUTE
    assert settings.upload_rate_limit_per_minute == UPLOAD_RATE_LIMIT_PER_MINUTE


def test_load_rag_api_settings_reads_query_rate_limit_from_env(monkeypatch):
    monkeypatch.setenv("QUERY_RATE_LIMIT_PER_MINUTE", "7")

    settings = load_rag_api_settings()

    assert settings.query_rate_limit_per_minute == 7
    # Upload's limit is unaffected by the query env var.
    assert settings.upload_rate_limit_per_minute == UPLOAD_RATE_LIMIT_PER_MINUTE


def test_load_rag_api_settings_reads_upload_rate_limit_from_env(monkeypatch):
    monkeypatch.setenv("UPLOAD_RATE_LIMIT_PER_MINUTE", "3")

    settings = load_rag_api_settings()

    assert settings.upload_rate_limit_per_minute == 3
    assert settings.query_rate_limit_per_minute == QUERY_RATE_LIMIT_PER_MINUTE


def test_load_rag_api_settings_rejects_non_integer_query_rate_limit(monkeypatch):
    monkeypatch.setenv("QUERY_RATE_LIMIT_PER_MINUTE", "not-a-number")

    with pytest.raises(MissingEnvironmentVariable):
        load_rag_api_settings()


def test_load_rag_api_settings_rejects_non_integer_upload_rate_limit(monkeypatch):
    monkeypatch.setenv("UPLOAD_RATE_LIMIT_PER_MINUTE", "not-a-number")

    with pytest.raises(MissingEnvironmentVariable):
        load_rag_api_settings()


def test_load_rag_api_settings_treats_empty_string_rate_limit_env_as_unset(monkeypatch):
    monkeypatch.setenv("QUERY_RATE_LIMIT_PER_MINUTE", "")

    settings = load_rag_api_settings()

    assert settings.query_rate_limit_per_minute == QUERY_RATE_LIMIT_PER_MINUTE


# --- Integration tests through the FastAPI dependency / routes -------------


@pytest.fixture
def set_rate_limit_settings(monkeypatch):
    """Factory fixture: patch `load_rag_api_settings` (as seen by
    `rag_api.rate_limiter`) to return a `RagApiSettings` with the given
    rate-limit overrides, so tests don't need to fire 20+/5+ requests to
    observe a 429. Returns the function to call with keyword overrides
    (e.g. `query_rate_limit_per_minute=2`); any field not overridden keeps
    its normal default.
    """

    def _set(**overrides) -> RagApiSettings:
        settings = RagApiSettings(
            openai_api_key="sk-test-key",
            internal_api_key="test-internal-api-key",
            **overrides,
        )
        monkeypatch.setattr("rag_api.rate_limiter.load_rag_api_settings", lambda: settings)
        return settings

    return _set


@pytest.fixture
def low_query_limit(set_rate_limit_settings) -> RagApiSettings:
    return set_rate_limit_settings(query_rate_limit_per_minute=2)


@pytest.fixture
def low_upload_limit(set_rate_limit_settings) -> RagApiSettings:
    return set_rate_limit_settings(upload_rate_limit_per_minute=2)


def _mock_query_dependencies(mocker):
    mocker.patch(
        "rag_api.query_parser.parse_query",
        return_value=ParsedQuery(
            rewritten_query="q",
            intent="lookup",
            date_from=None,
            date_to=None,
            document_type=None,
            entities=[],
        ),
    )
    mocker.patch("rag_pipeline.search", return_value=[])
    mocker.patch("rag_api.openai_client.ask_openai", return_value=("An answer.", []))


def test_query_endpoint_returns_429_with_retry_after_once_limit_exceeded(
    client, low_query_limit, mocker
):
    _mock_query_dependencies(mocker)

    for _ in range(2):
        response = client.post("/query", json={"question": "How much did I spend?"})
        assert response.status_code == 200

    response = client.post("/query", json={"question": "How much did I spend?"})

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
    assert "detail" in response.json()


def test_query_and_query_agent_share_the_same_rate_limit_bucket(
    client, low_query_limit, mocker
):
    _mock_query_dependencies(mocker)
    mocker.patch(
        "rag_api.routes.query.run_agent_query",
        return_value={"answer": "An answer.", "sources": []},
    )

    assert client.post("/query", json={"question": "q1"}).status_code == 200
    assert client.post("/query/agent", json={"question": "q2"}).status_code == 200

    # Both routes together already used up the shared 2-request bucket.
    response = client.post("/query", json={"question": "q3"})
    assert response.status_code == 429


def test_different_users_are_rate_limited_independently_through_the_route(
    client, low_query_limit, other_user_id, mocker
):
    _mock_query_dependencies(mocker)

    for _ in range(2):
        assert client.post("/query", json={"question": "q"}).status_code == 200
    assert client.post("/query", json={"question": "q"}).status_code == 429

    # A different X-User-Id has its own, untouched bucket.
    other_response = client.post(
        "/query",
        json={"question": "q"},
        headers={"X-User-Id": other_user_id},
    )
    assert other_response.status_code == 200


def test_upload_endpoint_returns_429_once_limit_exceeded(client, low_upload_limit, mocker):
    mocker.patch("rag_pipeline.create_pending_document", return_value="new-doc-id")
    mocker.patch("rag_pipeline.process_document")

    for _ in range(2):
        response = client.post(
            "/upload",
            files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )
        assert response.status_code == 201

    response = client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_query_and_upload_limits_are_independent_buckets(
    client, set_rate_limit_settings, mocker
):
    # Both limits are set together on the same patched settings instance -
    # using both the `low_query_limit` and `low_upload_limit` fixtures
    # together would not compose (the second would just overwrite the
    # first's monkeypatch with a settings instance that has upload's field
    # overridden but query's back at its default).
    set_rate_limit_settings(query_rate_limit_per_minute=2, upload_rate_limit_per_minute=2)
    _mock_query_dependencies(mocker)
    mocker.patch("rag_pipeline.create_pending_document", return_value="new-doc-id")
    mocker.patch("rag_pipeline.process_document")

    # Exhaust the query bucket only.
    for _ in range(2):
        assert client.post("/query", json={"question": "q"}).status_code == 200
    assert client.post("/query", json={"question": "q"}).status_code == 429

    # Upload's separate bucket is unaffected.
    response = client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    assert response.status_code == 201


# --- Redis-backed path (rag_pipeline.redis_support) -------------------------
#
# `FakeRedis` re-implements just enough of redis-py's sorted-set surface
# (ZREMRANGEBYSCORE/ZCARD/ZRANGE/ZADD/EXPIRE) to actually execute
# `rate_limiter._SLIDING_WINDOW_LUA`'s logic in pure Python, so these tests
# exercise the real algorithm end-to-end (not just "was eval() called")
# without needing a live Redis server. Time is driven by a fake `time.time`
# clock (mirroring `_FakeClock`/`fake_clock` above, but for the Redis path's
# wall-clock timestamps), so window-elapsed behavior is deterministic here
# too.


class _FakeWallClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def fake_wall_clock(monkeypatch) -> _FakeWallClock:
    clock = _FakeWallClock()
    monkeypatch.setattr(rate_limiter.time, "time", clock)
    return clock


class FakeRedis:
    """A tiny in-memory stand-in for `redis.Redis`, implementing exactly the
    commands `rate_limiter._SLIDING_WINDOW_LUA` uses against a sorted set,
    plus `scan_iter`/`delete` for `reset_for_tests`. `eval()` interprets the
    *specific* script this module calls it with by running the equivalent
    Python logic directly - not a general Lua interpreter.
    """

    def __init__(self) -> None:
        self._sorted_sets: dict[str, dict[str, float]] = {}

    def eval(self, script, numkeys, *keys_and_args):
        assert script is rate_limiter._SLIDING_WINDOW_LUA
        assert numkeys == 1
        key, now_repr, window_repr, max_requests_repr, member = keys_and_args
        now = float(now_repr)
        window_seconds = float(window_repr)
        max_requests = int(max_requests_repr)
        window_start = now - window_seconds

        members = self._sorted_sets.setdefault(key, {})
        for stale_member, score in list(members.items()):
            if score <= window_start:
                del members[stale_member]

        if len(members) >= max_requests:
            oldest_score = min(members.values())
            return repr(oldest_score - window_start).encode()

        members[member] = now
        return b"0"

    def scan_iter(self, match: str):
        # `match` here is always a literal "prefix*" glob from this module.
        assert match.endswith("*")
        prefix = match[:-1]
        return [key for key in self._sorted_sets if key.startswith(prefix)]

    def delete(self, key: str) -> None:
        self._sorted_sets.pop(key, None)


@pytest.fixture
def fake_redis_client(monkeypatch) -> FakeRedis:
    """Monkeypatch `redis_support.get_redis_client` (as seen by
    `rag_api.rate_limiter`) to return a fresh `FakeRedis` instance, so
    `_SlidingWindowRateLimiter.check` takes the Redis-backed path instead of
    the in-process fallback."""
    client = FakeRedis()
    monkeypatch.setattr(redis_support, "get_redis_client", lambda: client)
    return client


def test_redis_path_used_when_configured(fake_redis_client, fake_wall_clock):
    limiter = _SlidingWindowRateLimiter(namespace="test")

    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None

    # Recorded in the fake Redis store, not the in-process dict.
    assert limiter._requests == {}
    assert any(
        key.startswith("ratelimit:test:") for key in fake_redis_client._sorted_sets
    )


def test_redis_path_enforces_the_configured_limit(fake_redis_client, fake_wall_clock):
    limiter = _SlidingWindowRateLimiter(namespace="test")

    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None

    retry_after = limiter.check(USER_ID, max_requests=5)
    assert retry_after is not None
    assert retry_after > 0


def test_redis_path_window_resets_after_it_elapses(fake_redis_client, fake_wall_clock):
    limiter = _SlidingWindowRateLimiter(namespace="test", window_seconds=60.0)

    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None
    assert limiter.check(USER_ID, max_requests=5) is not None

    fake_wall_clock.advance(60.0 + 0.001)

    assert limiter.check(USER_ID, max_requests=5) is None


def test_redis_path_different_users_have_independent_limits(fake_redis_client, fake_wall_clock):
    limiter = _SlidingWindowRateLimiter(namespace="test")

    for _ in range(3):
        assert limiter.check(USER_ID, max_requests=3) is None
    assert limiter.check(USER_ID, max_requests=3) is not None

    assert limiter.check(OTHER_USER_ID, max_requests=3) is None


def test_redis_path_query_and_upload_limiters_use_separate_namespaces(
    fake_redis_client, fake_wall_clock
):
    for _ in range(20):
        assert rate_limiter._query_limiter.check(USER_ID, max_requests=20) is None
    assert rate_limiter._query_limiter.check(USER_ID, max_requests=20) is not None

    # The upload limiter for the same user, in a different Redis namespace,
    # is untouched.
    assert rate_limiter._upload_limiter.check(USER_ID, max_requests=5) is None


def test_reset_for_tests_clears_redis_state(fake_redis_client, fake_wall_clock):
    limiter = _SlidingWindowRateLimiter(namespace="test")
    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None
    assert limiter.check(USER_ID, max_requests=5) is not None

    limiter.reset_for_tests()

    assert limiter.check(USER_ID, max_requests=5) is None


def test_falls_back_to_local_when_redis_not_configured(fake_clock, monkeypatch):
    """Without REDIS_URL/a configured client, `get_redis_client()` returns
    None and the limiter must still work via its in-process fallback."""
    monkeypatch.setattr(redis_support, "get_redis_client", lambda: None)
    limiter = _SlidingWindowRateLimiter(namespace="test")

    for _ in range(5):
        assert limiter.check(USER_ID, max_requests=5) is None
    assert limiter.check(USER_ID, max_requests=5) is not None
    assert USER_ID in limiter._requests

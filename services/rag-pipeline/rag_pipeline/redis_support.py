"""Shared Redis client factory backing the shared-state modules that need
cross-process coordination once more than one instance of a service is
running: `rag_pipeline.dashboard_cache` (per-user dashboard TTL cache) and
`rag_api.rate_limiter` (per-user request-rate limiter).

Both of those modules started out as small, hand-rolled, per-process
dict-based stores (see their own docstrings) - correct for a single running
process, but each process gets its own independent state once a service is
scaled to more than one worker/task (e.g. `desired_count > 1` on Fargate):
independent rate-limit counters mean the effective limit becomes
(configured limit) x (process count), and independent caches mean different
processes can serve different (stale vs. fresh) cached values for the same
user depending on which one handles a given request.

This module centralizes the one bit of shared logic both need: obtaining a
`redis.Redis` client when a shared store is actually configured, so multiple
processes/tasks can coordinate through it instead of independent in-memory
state. Lives in `rag_pipeline` (not `rag_api`) so it's defined once and
shared - `rag_api` already depends on `rag_pipeline` as a path dependency
(see rag-api/pyproject.toml), so `rag_api.rate_limiter` can reuse this
without needing its own copy or its own direct dependency on `redis-py`.

Configuration is entirely optional and controlled by a single `REDIS_URL`
environment variable (e.g. `redis://user:password@host:6379/0`, or
`rediss://...` for TLS - see redis-py's `Redis.from_url` for the full URL
scheme). When unset (the default for local dev and the existing test
suites), `get_redis_client()` returns `None` and callers are expected to
fall back to their existing in-process dict/Lock implementation - this
module deliberately does not require a live Redis server to import or use
rag_pipeline/rag_api at all, matching this repo's existing "zero external
dependencies for local dev/tests" convention (see e.g.
rag_api/config.py's AGENT_CHECKPOINT_DB_URL handling for the same pattern).
"""

from __future__ import annotations

import os
from functools import lru_cache

import redis

# Env var name read by `get_redis_client()`. A single shared name (not
# per-service) since both rag-api and rag-pipeline are meant to point at the
# same Redis instance for this to actually coordinate anything.
REDIS_URL_ENV_VAR = "REDIS_URL"


@lru_cache(maxsize=None)
def _client_for_url(url: str) -> "redis.Redis":
    """Build (and cache, per distinct URL) a `redis.Redis` client.

    `redis.Redis.from_url` does not eagerly open a connection - it just
    builds a connection pool - so constructing this is cheap and safe to do
    once and reuse. `decode_responses` is deliberately left at its default
    (False, i.e. bytes back from GET/etc.): `dashboard_cache` stores
    pickled bytes, which would round-trip incorrectly through a decoding
    layer, and `rag_api.rate_limiter` decodes/parses the (plain ASCII)
    values it cares about itself.
    """
    return redis.Redis.from_url(url)


def get_redis_client(redis_url: str | None = None) -> "redis.Redis | None":
    """Return a shared `redis.Redis` client, or `None` if no shared store is
    configured.

    Reads `REDIS_URL` from the environment on every call (not frozen at
    import time), mirroring this codebase's existing convention for
    optional, environment-driven config (e.g.
    `rag_api.config.load_rag_api_settings` re-reading its env vars per
    call) - this keeps local dev/tests able to toggle Redis on and off via
    `monkeypatch.setenv`/`monkeypatch.delenv` without needing a process
    restart, and lets a real deployment be reconfigured without a code
    change.

    `redis_url` is an optional explicit override (mainly for tests); when
    omitted, falls back to the `REDIS_URL` environment variable.
    """
    url = redis_url if redis_url is not None else os.environ.get(REDIS_URL_ENV_VAR)
    if not url:
        return None
    return _client_for_url(url)


def reset_for_tests() -> None:
    """Drop all cached clients. Test-isolation helper only: without this,
    a client built against one test's monkeypatched `REDIS_URL` (e.g. one
    pointed at a mock/fake) would keep being returned by `_client_for_url`'s
    cache for a later test that reuses the same URL string with a different
    mock installed."""
    _client_for_url.cache_clear()

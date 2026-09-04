"""In-process, per-user rate limiting for rag-api's costly, abusable routes.

`POST /query` and `POST /query/agent` (rag_api/routes/query.py) each trigger
at least one paid OpenAI call per request (query parsing plus answer
synthesis; `/query/agent` can also loop retrieval via LangGraph), and
`POST /upload` (rag_api/routes/documents.py) parses/embeds/stores an entire
document. None of them are bounded today, so an authenticated user (or a
buggy client retrying in a loop) can call them arbitrarily fast. This module
adds a minimal per-user request-rate limit in front of each, keyed on the
already-verified `user_id` from `rag_api.auth.require_user_id` - see that
module's docstring for why this id can be trusted here without rag-api
re-verifying it itself.

Originally (and still, by default) a small hand-rolled per-key
sliding-window log (a dict keyed by `user_id` storing a `collections.deque`
of `time.monotonic()` timestamps) rather than pulling in a rate-limiting
library (e.g. `slowapi`/`limits`) or an external store (Redis) - a limiter
this small doesn't warrant a new dependency by itself, following the same
"small hand-rolled dict, no new dependency" precedent as
`rag_pipeline.dashboard_cache`. That in-process log is still exactly what's
used when no shared store is configured (local dev, and every existing
test in this suite).

Sliding window log, not a fixed window counter: a fixed window (e.g. "the
count resets at the top of each minute") lets a client send up to roughly
2x its intended limit in a short burst straddling the window boundary - the
last `max_requests` of one window immediately followed by the first
`max_requests` of the next. A sliding window log instead tracks the exact
timestamp of every request still within the trailing `WINDOW_SECONDS` and
counts against those, so it doesn't have that boundary-burst weakness -
the limit holds over *any* trailing window, not just calendar-aligned ones.
The tradeoff is a little more per-user memory (up to `max_requests`
timestamps instead of a single integer), which is bounded and small: once a
user is at their limit, further requests within the window are rejected
outright and never get appended, so a key's deque can never hold more than
`max_requests` entries.

rag-api's route handlers here are sync `def`s, which FastAPI runs in a
threadpool, so concurrent requests for the same user can race on the same
deque; each limiter's dict is guarded by a `threading.Lock`, exactly like
`dashboard_cache._TTLCache`.

The in-process log above is a per-process limiter: it does not coordinate
across multiple uvicorn/gunicorn workers or Fargate tasks, so with more
than one worker process each one enforces its own independent limit - a
user spread across N processes could exceed the intended aggregate rate by
up to Nx. See GitHub issue #16.

`_SlidingWindowRateLimiter.check` closes that gap when `REDIS_URL` is
configured (see `rag_pipeline.redis_support`): it re-checks on every call
whether a shared Redis client is available and, if so, enforces the exact
same sliding-window-log semantics (matching the trailing-window boundary
behavior described above, not a fixed-window approximation) atomically via
a small Lua script (`_SLIDING_WINDOW_LUA`) executed server-side with
`EVAL`, using a Redis sorted set per key (score = request timestamp) in
place of the in-process `deque`. Redis's single-threaded command execution
makes the script's remove-expired / count / conditionally-add sequence
atomic the same way the in-process version's `threading.Lock` does, so this
preserves the limiter's exact behavior instead of approximating it - just
backed by a store every process/task can see, instead of one only this
process can see. `redis-py` (already a new dependency added for this - see
rag-pipeline/pyproject.toml, which is where `rag_pipeline.redis_support`
lives) is the natural, official Redis client; nothing already in this
project's dependency tree provides one.

Known limitation, accepted for now, mirroring dashboard_cache.py's
equivalent: the in-process fallback's dict of per-user deques grows by one
entry per distinct user ever seen by this process, with no eviction - a
user who stops making requests leaves behind an (eventually empty, once its
entries age out) deque that just sits there. For this app's expected user
counts this is a small, bounded amount of memory per long-running process,
not worth the added complexity of an eviction policy today. The Redis path
avoids this specific issue (each user's sorted set naturally empties out
and gets a fresh `EXPIRE` each time it's touched, so an abandoned key
simply expires), but is out of scope to backport to the in-process
fallback.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections import deque

from fastapi import Depends, HTTPException, status

from rag_api.auth import require_user_id
from rag_api.config import load_rag_api_settings
from rag_pipeline import redis_support

# Lua script executed atomically via Redis EVAL, implementing the exact same
# trailing-sliding-window-log algorithm as `_SlidingWindowRateLimiter.check`'s
# in-process path (see this module's docstring), against a Redis sorted set
# keyed by `KEYS[1]`, with each member's score set to the (wall-clock, since
# multiple processes/hosts must agree on it - unlike `time.monotonic()`)
# timestamp of the request it represents.
#
# ARGV[1] = now (float, seconds since epoch, i.e. `time.time()`)
# ARGV[2] = window_seconds (float)
# ARGV[3] = max_requests (integer)
# ARGV[4] = member (a unique string identifying this request - `time.time()`
#           alone is not guaranteed unique across concurrent callers, and a
#           sorted set requires unique members)
#
# Returns the number of seconds (as a Lua number, coerced to a Redis bulk
# string by EVAL) the caller must wait before its next request would be
# allowed, or "0" if the request was allowed (and has already been
# recorded) - mirrored in Python by treating a non-positive result as
# "allowed".
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]
local window_start = now - window_seconds

redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local count = redis.call('ZCARD', key)

if count >= max_requests then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local oldest_score = tonumber(oldest[2])
    return tostring(oldest_score - window_start)
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window_seconds) + 1)
return '0'
"""

# Trailing-window length shared by every limiter in this module. Kept as a
# single named constant rather than a per-limiter constructor argument,
# since every current use case here wants "requests per minute" - only the
# max-requests count actually needs to vary per endpoint/deployment (see
# RagApiSettings.query_rate_limit_per_minute/upload_rate_limit_per_minute).
WINDOW_SECONDS = 60.0


class _SlidingWindowRateLimiter:
    """A tiny per-key sliding-window request counter.

    In-process fallback storage is `key -> deque[timestamp]`; when
    `REDIS_URL` is configured, storage instead becomes a Redis sorted set
    per key (see this module's docstring and `_SLIDING_WINDOW_LUA`) so the
    limit is enforced across every process/task sharing that Redis
    instance, not just this one.

    `check(key, max_requests)` records a request for `key` and returns
    `None` if it's within `max_requests` over the trailing `WINDOW_SECONDS`.
    If the limit has already been reached, the request is *not* recorded,
    and the number of seconds until the caller's next request would be
    allowed is returned instead.

    `namespace` scopes this instance's Redis keys (e.g. `"query"` vs.
    `"upload"`), so the two module-level limiters below - and
    `rag_pipeline.dashboard_cache`'s own keys in the same Redis instance -
    never collide with each other.
    """

    def __init__(self, namespace: str = "default", window_seconds: float = WINDOW_SECONDS) -> None:
        self._namespace = namespace
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._requests: dict[str, deque[float]] = {}

    def check(self, key: str, max_requests: int) -> float | None:
        client = redis_support.get_redis_client()
        if client is not None:
            return self._check_redis(client, key, max_requests)
        return self._check_local(key, max_requests)

    def _check_local(self, key: str, max_requests: int) -> float | None:
        now = time.monotonic()
        window_start = now - self._window_seconds
        with self._lock:
            timestamps = self._requests.setdefault(key, deque())
            # Drop everything that's aged out of the trailing window. Since
            # entries are appended in increasing timestamp order, the oldest
            # (leftmost) entries always age out first.
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= max_requests:
                # The oldest timestamp still in the window is the next one
                # to age out, freeing a slot - the caller can retry once it
                # does. Always > window_start here (anything <= window_start
                # was just popped above), so this is always > 0.
                return math.ceil(timestamps[0] - window_start)

            timestamps.append(now)
            return None

    def _redis_key(self, key: str) -> str:
        return f"ratelimit:{self._namespace}:{key}"

    def _check_redis(self, client: "redis_support.redis.Redis", key: str, max_requests: int) -> float | None:
        now = time.time()
        # Unique per call (time.time() alone isn't guaranteed unique across
        # concurrent callers, and ZADD requires unique members).
        member = f"{now!r}:{uuid.uuid4()}"
        result = client.eval(
            _SLIDING_WINDOW_LUA,
            1,
            self._redis_key(key),
            repr(now),
            repr(self._window_seconds),
            str(max_requests),
            member,
        )
        retry_after_seconds = float(result)
        if retry_after_seconds > 0:
            return math.ceil(retry_after_seconds)
        return None

    def reset_for_tests(self) -> None:
        """Wipe all tracked keys, both the in-process fallback and (if
        configured) this instance's Redis keys. Test-isolation helper only,
        mirroring `dashboard_cache._TTLCache.clear`."""
        with self._lock:
            self._requests.clear()
        client = redis_support.get_redis_client()
        if client is None:
            return
        for redis_key in client.scan_iter(match=self._redis_key("*")):
            client.delete(redis_key)


# Separate limiter instances (separate dicts/locks, and separate Redis key
# namespaces) for query vs. upload, since they have different costs and
# independently configured limits - a user maxing out one must not affect
# their remaining budget on the other.
_query_limiter = _SlidingWindowRateLimiter(namespace="query")
_upload_limiter = _SlidingWindowRateLimiter(namespace="upload")

# /readyz (rag_api/routes/health.py) is deliberately unauthenticated - it's
# polled by the ALB's target group health check, which has no way to send
# the X-Internal-Api-Key header - so it can't be keyed per-user like
# _query_limiter/_upload_limiter above. Anyone who can reach the public
# CloudFront distribution can hit it at an arbitrary rate, and every hit
# triggers a real Supabase round-trip (see health.py's `_check_supabase`),
# so this is a single global bucket (fixed key, shared across every caller)
# rather than per-user, with its own short 1-second window: generous enough
# not to interfere with the ALB's own health-check cadence (every ~30s per
# infra/rag_api_stack.py) while still capping the worst case an abusive
# caller can force onto Supabase.
_READYZ_RATE_LIMIT_KEY = "readyz"
_readyz_limiter = _SlidingWindowRateLimiter(window_seconds=1.0)


def _enforce(limiter: _SlidingWindowRateLimiter, user_id: str, max_requests: int) -> None:
    retry_after_seconds = limiter.check(user_id, max_requests)
    if retry_after_seconds is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down and try again shortly.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


def require_query_rate_limit(user_id: str = Depends(require_user_id)) -> None:
    """FastAPI dependency: enforce the per-user query rate limit.

    `POST /query` and `POST /query/agent` both pull this in via `Depends`
    and share the same limiter/bucket keyed only on `user_id` - both trigger
    a comparably costly OpenAI call per request, and sharing a bucket means
    a client can't dodge the limit by alternating between the two routes.
    Raises 429 with a `Retry-After` header once
    `settings.query_rate_limit_per_minute` requests have been made by this
    user within the trailing `WINDOW_SECONDS`.
    """
    settings = load_rag_api_settings()
    _enforce(_query_limiter, user_id, settings.query_rate_limit_per_minute)


def require_upload_rate_limit(user_id: str = Depends(require_user_id)) -> None:
    """FastAPI dependency: enforce the per-user upload rate limit.

    Kept as a separate limiter/bucket from `require_query_rate_limit`, since
    uploads are heavier and have their own, independently configured limit
    (`settings.upload_rate_limit_per_minute`).
    """
    settings = load_rag_api_settings()
    _enforce(_upload_limiter, user_id, settings.upload_rate_limit_per_minute)


def require_readyz_rate_limit() -> None:
    """FastAPI dependency: enforce a global (not per-user - see
    `_readyz_limiter`'s docstring above) request-rate limit on `/readyz`.

    No `user_id` dependency here, unlike `require_query_rate_limit`/
    `require_upload_rate_limit` above - `/readyz` is intentionally reachable
    without authentication, so there is no verified `user_id` to key on.
    Raises 429 with a `Retry-After` header once
    `settings.readyz_rate_limit_per_second` requests have been made by
    *anyone* within the trailing 1-second window.
    """
    settings = load_rag_api_settings()
    _enforce(_readyz_limiter, _READYZ_RATE_LIMIT_KEY, settings.readyz_rate_limit_per_second)


def reset_for_tests() -> None:
    """Wipe all limiters entirely. Test-isolation helper only: since these
    limiters are process-global module state, tests that reuse the same
    `user_id` across cases (as the existing query/upload route test suites
    do) would otherwise see rate-limit state leak between tests within the
    same window."""
    _query_limiter.reset_for_tests()
    _upload_limiter.reset_for_tests()
    _readyz_limiter.reset_for_tests()

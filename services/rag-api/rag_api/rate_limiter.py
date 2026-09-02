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

Deliberately a small hand-rolled per-key sliding-window log (a dict keyed by
`user_id` storing a `collections.deque` of `time.monotonic()` timestamps)
rather than pulling in a rate-limiting library (e.g. `slowapi`/`limits`) or
an external store (Redis) - a limiter this small doesn't warrant a new
dependency, following the same "small hand-rolled dict, no new dependency"
precedent as `rag_pipeline.dashboard_cache`.

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

This is a per-process limiter: it does not coordinate across multiple
uvicorn/gunicorn workers or Fargate tasks, so with more than one worker
process each one enforces its own independent limit - a user spread across
N processes could exceed the intended aggregate rate by up to Nx. Accepted
for now for the same reason `dashboard_cache.py` accepts the equivalent
limitation for its cache: a true global limiter would need a shared store
(Redis or similar) this service doesn't otherwise depend on. Would need
revisiting if this service is ever scaled to multiple workers/tasks in a
way where this limitation actually bites in practice.

Known limitation, accepted for now, mirroring dashboard_cache.py's
equivalent: the dict of per-user deques grows by one entry per distinct
user ever seen by this process, with no eviction - a user who stops making
requests leaves behind an (eventually empty, once its entries age out)
deque that just sits there. For this app's expected user counts this is a
small, bounded amount of memory per long-running process, not worth the
added complexity of an eviction policy today.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque

from fastapi import Depends, HTTPException, status

from rag_api.auth import require_user_id
from rag_api.config import load_rag_api_settings

# Trailing-window length shared by every limiter in this module. Kept as a
# single named constant rather than a per-limiter constructor argument,
# since every current use case here wants "requests per minute" - only the
# max-requests count actually needs to vary per endpoint/deployment (see
# RagApiSettings.query_rate_limit_per_minute/upload_rate_limit_per_minute).
WINDOW_SECONDS = 60.0


class _SlidingWindowRateLimiter:
    """A tiny per-key sliding-window request counter: `key -> deque[timestamp]`.

    `check(key, max_requests)` records a request for `key` and returns
    `None` if it's within `max_requests` over the trailing `WINDOW_SECONDS`.
    If the limit has already been reached, the request is *not* recorded,
    and the number of seconds until the caller's next request would be
    allowed is returned instead.
    """

    def __init__(self, window_seconds: float = WINDOW_SECONDS) -> None:
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._requests: dict[str, deque[float]] = {}

    def check(self, key: str, max_requests: int) -> float | None:
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

    def reset_for_tests(self) -> None:
        """Wipe all tracked keys. Test-isolation helper only, mirroring
        `dashboard_cache._TTLCache.clear`."""
        with self._lock:
            self._requests.clear()


# Separate limiter instances (separate dicts/locks) for query vs. upload,
# since they have different costs and independently configured limits - a
# user maxing out one must not affect their remaining budget on the other.
_query_limiter = _SlidingWindowRateLimiter()
_upload_limiter = _SlidingWindowRateLimiter()

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

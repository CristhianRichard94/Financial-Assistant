"""Short-TTL cache for the Overview dashboard's aggregates.

`dashboard.get_dashboard_summary`/`get_recent_activity` each run several
live Supabase queries (see dashboard.py's module docstring), all of which
get re-run on every dashboard load with no caching anywhere in the stack.
This module adds a minimal per-user TTL cache in front of both, so rapid
repeat loads (tab refocus, navigating back to Overview, React re-renders)
within the TTL window don't re-hit Supabase.

Originally (and still, by default) a small hand-rolled dict-based cache (a
dict keyed by cache key storing `(value, expires_at)`, using
`time.monotonic()`) rather than pulling in `cachetools` or Redis - a single
small cache like this doesn't warrant a new dependency by itself. That
in-process cache (`_TTLCache` below) is still exactly what's used when no
shared store is configured (local dev, and every existing test in this
suite), and is still guarded by a `threading.Lock` for the same reason as
before: rag-api's route handlers here are sync `def`s, which FastAPI runs
in a threadpool, so concurrent requests for the same user can race on the
same cache slot.

That in-process cache is a per-process cache: it does not coordinate across
multiple worker processes/machines, so with more than one worker a write
handled by one process won't invalidate another process's cached entry
until that entry's TTL naturally expires - or, once this service is scaled
to multiple Fargate tasks, a client can be served a stale answer indefinitely
depending on which task happens to handle a given request, since each task's
cache only ever sees its own process's writes/invalidations. See GitHub
issue #16.

`_HybridTTLCache` (used by the module-level `_summary_cache`/
`_activity_cache` below) closes that gap: when `REDIS_URL` is configured
(see `rag_pipeline.redis_support`), every `get_or_compute`/`invalidate`/
`invalidate_prefix` call is served from a shared Redis SETEX'd key instead
of this process's own dict, so all processes/tasks see the same cached
value and the same invalidations. `redis-py` (already a new dependency
added for this - see rag-pipeline/pyproject.toml) is the natural, official
Redis client; nothing already in this project's dependency tree provides
one. `REDIS_URL` is re-checked on every call (not frozen at import time),
so a single running process transparently uses whichever backend is
currently configured, and local dev/tests need zero setup to keep using the
in-process fallback.

Known, deliberately accepted limitation of the Redis-backed path: unlike
the in-process `_TTLCache` (guarded end-to-end by a single `threading.Lock`
per cache), the Redis path does not replicate `_TTLCache`'s per-key
generation / per-prefix epoch guard against a `compute()` call racing a
concurrent invalidation (see `_TTLCache.get_or_compute`'s docstring) - a
`compute()` in flight when an `invalidate`/`invalidate_prefix` for the same
key lands elsewhere can still write its (now-stale) result back with a
fresh TTL. A fully race-proof cross-process version of that same guard
would need a Redis transaction/Lua script keyed on a shared generation
counter; not implemented here as this is still a bounded, self-healing
staleness window (at most `TTL_SECONDS`), same order of risk this module
already accepted for the multi-process case before Redis existed here at
all - not a new regression, just not a full fix. Revisit if this proves to
bite in practice.

Known limitation, accepted for now (in-process fallback only): both
in-process caches' dicts (entries, per-key generations, and - for the
activity cache - per-prefix epochs) grow by one entry per distinct user
(and, for activity's entries/generations, per distinct user/limit pair)
ever seen by this process, with no eviction beyond TTL expiry replacing an
existing entry in place - there's no cap or LRU eviction. For this app's
expected user counts this is a small, bounded amount of memory per
long-running process, not worth the added complexity of an eviction policy
today; would need revisiting if the user base grows by orders of magnitude.
"""

from __future__ import annotations

import pickle
import threading
import time
from typing import Callable, Generic, TypeVar

from rag_pipeline import redis_support

# Kept as a named constant so it's easy to tune later.
TTL_SECONDS = 30.0

_T = TypeVar("_T")


class _TTLCache(Generic[_T]):
    """A tiny per-key TTL cache: `key -> (value, expires_at)`.

    Also tracks:
    - a per-key generation counter, bumped by `invalidate(key)`, so a
      `compute()` call already in flight when its exact key gets
      invalidated can't "un-invalidate" the entry afterwards by writing
      back the stale value it fetched before the invalidation happened
      (see `get_or_compute`).
    - a per-prefix epoch counter, bumped by `invalidate_prefix(prefix)`,
      covering the same race for a key that has *never been seen before*
      (e.g. a user's first-ever `get_recent_activity` call for a given
      `limit` after a process restart). `invalidate_prefix` can evict
      already-tracked keys directly, but it can't retroactively bump a
      per-key generation for a concrete `"{user_id}:{limit}"` key it
      doesn't know about yet - `limit` varies by caller and isn't
      enumerable in advance. The per-prefix epoch closes that gap:
      `get_or_compute` callers that pass a `prefix` also get checked
      against it, so even a brand-new key's in-flight `compute()` result
      is discarded if that prefix was invalidated while it was running.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[_T, float]] = {}
        self._generations: dict[str, int] = {}
        self._prefix_epochs: dict[str, int] = {}

    def get_or_compute(
        self, key: str, compute: Callable[[], _T], prefix: str | None = None
    ) -> _T:
        """Return the cached value for `key` if still fresh, otherwise call
        `compute()` and cache its result.

        `prefix` is optional and only needed by callers whose keys can also
        be evicted in bulk via `invalidate_prefix` (e.g. the activity
        cache's `"{user_id}:{limit}"` keys, invalidated by `user_id`) - it
        guards a fresh `compute()` result against a same-prefix
        invalidation that raced it, even for a key never seen before.
        """
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached[1] > now:
                return cached[0]
            generation = self._generations.get(key, 0)
            prefix_epoch = self._prefix_epochs.get(prefix, 0) if prefix is not None else None

        # Deliberately computed outside the lock: `compute()` does network
        # I/O (a Supabase call), and holding the lock across it would block
        # every other user's cache lookups on this same cache instance for
        # the duration of that call. Two concurrent requests for the same
        # uncached key may both compute and one write "wins" - an
        # acceptable occasional cache-stampede for a 30s soft cache, not a
        # correctness issue.
        value = compute()

        with self._lock:
            # If this key was invalidated directly, or its prefix was bulk-
            # invalidated, while `compute()` was in flight (generation/epoch
            # moved on since the snapshot above), discard the write: it
            # reflects data read before that invalidation and would
            # otherwise re-populate the cache with a stale value for a
            # fresh TTL window right after it was correctly evicted. The
            # caller who triggered this particular `compute()` still gets
            # its (now slightly stale, but already-in-hand) `value` back -
            # only the cache write is skipped.
            generation_unchanged = self._generations.get(key, 0) == generation
            epoch_unchanged = (
                prefix is None or self._prefix_epochs.get(prefix, 0) == prefix_epoch
            )
            if generation_unchanged and epoch_unchanged:
                self._entries[key] = (value, time.monotonic() + self._ttl_seconds)
        return value

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)
            self._generations[key] = self._generations.get(key, 0) + 1

    def invalidate_prefix(self, prefix: str) -> None:
        """Evict every entry whose key is `prefix` itself or starts with
        `prefix + ":"` (used for the activity cache, whose keys are
        `"{user_id}:{limit}"` since `limit` varies by caller). Matching is
        prefix-plus-separator, not a bare string prefix, so invalidating
        `"abc"` evicts `"abc"` and `"abc:20"` but never `"abc2:20"`.

        Also unconditionally bumps `prefix`'s own epoch counter, even when
        no keys currently match it, so a `get_or_compute(key, compute,
        prefix=prefix)` call for a not-yet-tracked key that's still in
        flight picks up this invalidation too (see the class docstring).
        """
        with self._lock:
            matching_keys = {
                key
                for key in (*self._entries, *self._generations)
                if key == prefix or key.startswith(f"{prefix}:")
            }
            for key in matching_keys:
                self._entries.pop(key, None)
                self._generations[key] = self._generations.get(key, 0) + 1
            self._prefix_epochs[prefix] = self._prefix_epochs.get(prefix, 0) + 1

    def clear(self) -> None:
        """Evict every entry, regardless of key. Test-isolation helper only -
        production code should always invalidate by key via
        `invalidate_dashboard_cache`, never wipe the whole cache."""
        with self._lock:
            self._entries.clear()
            self._generations.clear()
            self._prefix_epochs.clear()


class _HybridTTLCache(Generic[_T]):
    """Wraps a `_TTLCache` (in-process fallback) and transparently serves
    every call from Redis instead whenever `REDIS_URL` is configured (see
    `rag_pipeline.redis_support.get_redis_client`), re-checked on every
    call. See this module's docstring for the full rationale and the
    accepted limitation of the Redis path (no cross-process generation/
    epoch race guard).

    `namespace` prefixes every Redis key this instance touches (e.g.
    `"summary"`/`"activity"`), so the two module-level caches below never
    collide with each other or with `rag_api.rate_limiter`'s own keys in
    the same Redis instance.
    """

    def __init__(self, ttl_seconds: float, namespace: str) -> None:
        self._ttl_seconds = ttl_seconds
        self._namespace = namespace
        self._local: _TTLCache[_T] = _TTLCache(ttl_seconds)

    def _redis_key(self, key: str) -> bytes:
        return f"dashcache:{self._namespace}:{key}".encode()

    def get_or_compute(
        self, key: str, compute: Callable[[], _T], prefix: str | None = None
    ) -> _T:
        client = redis_support.get_redis_client()
        if client is None:
            return self._local.get_or_compute(key, compute, prefix=prefix)

        redis_key = self._redis_key(key)
        cached = client.get(redis_key)
        if cached is not None:
            return pickle.loads(cached)

        # Computed outside of any lock/transaction, same tradeoff as
        # `_TTLCache.get_or_compute` (see its docstring) - and, unlike that
        # local version, this path does not guard against a concurrent
        # invalidation racing this compute() (documented module-level
        # limitation above).
        value = compute()
        client.setex(redis_key, int(self._ttl_seconds), pickle.dumps(value))
        return value

    def invalidate(self, key: str) -> None:
        client = redis_support.get_redis_client()
        if client is None:
            self._local.invalidate(key)
            return
        client.delete(self._redis_key(key))

    def invalidate_prefix(self, prefix: str) -> None:
        client = redis_support.get_redis_client()
        if client is None:
            self._local.invalidate_prefix(prefix)
            return
        # Mirrors _TTLCache.invalidate_prefix's "prefix itself, or
        # prefix + ':' + anything" matching rule.
        client.delete(self._redis_key(prefix))
        scan_pattern = self._redis_key(f"{prefix}:*")
        for redis_key in client.scan_iter(match=scan_pattern):
            client.delete(redis_key)

    def clear(self) -> None:
        """Test-isolation helper only, mirroring `_TTLCache.clear`. Clears
        both the in-process fallback and (if configured) every Redis key
        under this instance's namespace."""
        self._local.clear()
        client = redis_support.get_redis_client()
        if client is None:
            return
        scan_pattern = self._redis_key("*")
        for redis_key in client.scan_iter(match=scan_pattern):
            client.delete(redis_key)


_summary_cache: _HybridTTLCache[object] = _HybridTTLCache(TTL_SECONDS, namespace="summary")
_activity_cache: _HybridTTLCache[object] = _HybridTTLCache(TTL_SECONDS, namespace="activity")


def cached_summary(user_id: str, compute: Callable[[], _T]) -> _T:
    """Return the cached `DashboardSummary` for `user_id` if still fresh,
    otherwise call `compute()`, cache its result for `TTL_SECONDS`, and
    return it.

    Not keyed on `Settings` - only on `user_id` - since within a single
    running process `Settings` is effectively constant (one Supabase
    project/environment per deployment); tests that vary `fake_settings`
    per call still get isolated results because `_reset_dashboard_cache`
    (see tests/conftest.py) clears both caches between tests.
    """
    return _summary_cache.get_or_compute(user_id, compute)


def cached_activity(user_id: str, limit: int, compute: Callable[[], _T]) -> _T:
    """Return the cached recent-activity list for `user_id`/`limit` if still
    fresh, otherwise call `compute()`, cache its result for `TTL_SECONDS`,
    and return it. Keyed on `limit` too since callers may ask for different
    page sizes.

    Passes `user_id` as the cache's `prefix` too, so a `compute()` call for
    a `limit` never seen before for this user is still protected against a
    same-user `invalidate_dashboard_cache` call racing it (see
    `_TTLCache.get_or_compute`'s docstring).
    """
    return _activity_cache.get_or_compute(f"{user_id}:{limit}", compute, prefix=user_id)


def invalidate_dashboard_cache(user_id: str) -> None:
    """Evict any cached summary/activity entries for `user_id`.

    Must be called immediately after a Supabase write that changes a user's
    `transactions` or `documents` rows successfully commits - document
    upload (both the synchronous pending-row creation and the background
    ingestion outcome) and document deletion - so the next dashboard load
    reflects the change instead of a stale cached value for up to
    `TTL_SECONDS`.
    """
    _summary_cache.invalidate(user_id)
    _activity_cache.invalidate_prefix(user_id)


def reset_for_tests() -> None:
    """Wipe both caches entirely. Test-isolation helper only: since these
    caches are process-global module state, tests that reuse the same
    `user_id` across cases (as the existing dashboard/ingest/documents test
    suites do) would otherwise see stale cached values leak between tests
    within the same TTL window."""
    _summary_cache.clear()
    _activity_cache.clear()

"""Retry-with-backoff helper for Supabase (postgrest-py) calls.

Why tenacity and not the supabase-py/postgrest-py client itself: unlike
`openai.OpenAI` (which has built-in `max_retries`/backoff for transient HTTP
errors - see `rag_pipeline/embeddings.py` and `rag_pipeline/parsing.py`'s
client construction), `supabase.create_client`/`ClientOptions` and the
underlying `postgrest-py` client expose only timeout configuration, no
retry/backoff mechanism at all (checked via `ClientOptions.__init__`'s
signature and `postgrest._sync.request_builder` - every `.execute()` call
either returns a response or raises immediately, with no retry hook). Hand
rolling an exponential-backoff-with-jitter loop would just reimplement what
`tenacity` already provides, so it's added as a new dependency here (see
rag-pipeline/pyproject.toml) rather than writing that loop by hand.

Only genuinely transient failures are retried:
- Network-level errors from httpx (the HTTP client postgrest-py/supabase-py
  is built on): connection failures and timeouts. These are ambiguous by
  nature (the request may or may not have reached the server), but a network
  blip is exactly the class of error this retry exists to absorb.
- `postgrest.exceptions.APIError` where the error can be attributed to an
  HTTP status of 429 (rate limited) or >=500 (server error). PostgREST/
  Supabase returns two different shapes here: when the response body isn't
  valid PostgREST JSON (typical of an infra-level 429/5xx from Supabase's
  edge/gateway), postgrest-py falls back to `APIError.code = <int status
  code>` (see `postgrest.exceptions.generate_default_error_message`). When
  the response *is* valid PostgREST JSON, `APIError.code` is a PostgREST/
  Postgres error code string (e.g. "PGRST116", or a numeric-looking Postgres
  SQLSTATE code like "23505" for a unique violation) describing a query or
  schema problem - those are not retried, since they are typically
  deterministic (bad filter, constraint violation, RLS denial, etc.), not
  transient. Only an `int` `code` is ever treated as an HTTP status; a `str`
  is never treated as one even if it happens to consist only of digits.

Explicitly NOT retried: 4xx errors (bad request, auth, not-found, unique/
check constraint violations, RLS denials) - retrying those would just repeat
the same failure and needlessly delay the caller.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

import httpx
from postgrest.exceptions import APIError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
)

T = TypeVar("T")

# Transient network-level errors: connection failures and any kind of
# timeout (connect/read/write/pool) raised by the httpx client underneath
# postgrest-py/supabase-py.
_TRANSIENT_HTTPX_ERRORS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)

# Cap: at most 3 attempts total (1 initial + 2 retries), and never spend more
# than ~8s total retrying, so a real outage still fails fast enough for
# callers' existing graceful-degradation paths (e.g. rag_api's /query
# fallback reply, see rag_api/routes/query.py) to kick in for real, rather
# than hanging behind a long retry loop.
_MAX_ATTEMPTS = 3
_MAX_RETRY_SECONDS = 8


def _status_code_from_api_error(exc: APIError) -> int | None:
    """Best-effort extraction of an HTTP status code from an APIError.

    `APIError.code` is only an HTTP status code (an `int`) when postgrest-py
    fell back to `generate_default_error_message` (non-JSON error body, i.e.
    an infra-level error rather than a structured PostgREST/Postgres error) -
    see this module's docstring. A `str` `code` is always a PostgREST/
    Postgres error code (e.g. "PGRST116", or a numeric-looking Postgres
    SQLSTATE like "23505" for a unique violation) and must NOT be treated as
    an HTTP status even when it happens to consist only of digits - it isn't
    one. Returns None when `code` isn't a status code at all.
    """
    code = exc.code
    if isinstance(code, int):
        return code
    return None


def _is_transient_supabase_error(exc: BaseException) -> bool:
    if isinstance(exc, _TRANSIENT_HTTPX_ERRORS):
        return True
    if isinstance(exc, APIError):
        status_code = _status_code_from_api_error(exc)
        if status_code is not None:
            return status_code == 429 or status_code >= 500
    return False


_supabase_retry = retry(
    retry=retry_if_exception(_is_transient_supabase_error),
    stop=stop_after_attempt(_MAX_ATTEMPTS) | stop_after_delay(_MAX_RETRY_SECONDS),
    wait=wait_exponential_jitter(initial=0.25, max=2),
    reraise=True,
)


def execute_with_retry(builder: Any) -> Any:
    """Call `builder.execute()`, retrying transient failures with backoff.

    `builder` is any postgrest-py query/RPC builder (the object returned by
    `supabase.table(...)...` or `supabase.rpc(...)` chains, right before
    `.execute()` would normally be called). Non-transient errors (4xx,
    structured PostgREST/Postgres errors) and retry exhaustion both propagate
    to the caller unchanged - callers keep their existing error handling
    (e.g. rag_api's routes turning this into a 502 with a graceful fallback).
    """

    @_supabase_retry
    def _run() -> Any:
        return builder.execute()

    return _run()


def with_retry(fn: Callable[[], T]) -> T:
    """Like `execute_with_retry`, but for an arbitrary zero-arg callable
    instead of a query builder (e.g. wrapping a call site that doesn't fit
    the `builder.execute()` shape).
    """

    @_supabase_retry
    def _run() -> T:
        return fn()

    return _run()

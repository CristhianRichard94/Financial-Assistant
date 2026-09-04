"""Liveness/readiness endpoints for the ALB health check.

`/healthz` is deliberately a bare liveness check - no auth and no downstream
dependency checks - it only needs to prove the process is up and serving
requests. It stays wired to the ECS container health check
(infra/rag_api_stack.py's `ContainerImage`/task definition uses Docker's
HEALTHCHECK, which needs a cheap, always-fast probe).

`/readyz` is a separate readiness check that verifies this task can actually
serve traffic, not just that the process is alive: a task can be up and
answering `/healthz` while unable to reach Supabase (network partition,
expired/rotated credentials, RLS misconfiguration), in which case every real
request would fail even though the bare liveness check reports healthy. The
ALB's target group health check (infra/rag_api_stack.py) points at `/readyz`
so a task in that state gets pulled out of rotation instead of keep getting
traffic.

`/readyz` intentionally does NOT check OpenAI reachability. Unlike the
Supabase check (a cheap `select` against a table this service already reads
on nearly every request), there's no equivalent free/trivial OpenAI call:
even the cheapest read-only endpoint (e.g. `GET /v1/models`) is a real
network round-trip to a third-party API, and the ALB polls this endpoint on
a short fixed interval (by default every 30s per target) for as long as the
task is running - multiplied across however many tasks/AZs are deployed,
that's a non-trivial, unbounded volume of extra outbound calls purely for
health checks, for a dependency that (unlike Supabase) this service already
handles failures from gracefully per-request (see rag_api/routes/query.py)
rather than needing the ALB to pull the task out of rotation over it. If
OpenAI degrades, in-flight requests fail with a normal error response; that's
an acceptable tradeoff against paying for/rate-limiting against OpenAI on
every health-check interval, on every task, indefinitely.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

import rag_pipeline
from fastapi import APIRouter, Depends, Response

from rag_api.config import READYZ_SUPABASE_TIMEOUT_SECONDS
from rag_api.rate_limiter import require_readyz_rate_limit

router = APIRouter()

# Sentinel user id used purely to exercise a real Supabase round-trip (a
# `select ... where user_id = ...` against the `documents` table) without
# depending on any real user's data existing. This UUID is never expected to
# match a real user, so the query always returns zero rows on success - the
# check only cares that the query executes at all, not what it returns.
_READYZ_PROBE_USER_ID = "00000000-0000-0000-0000-000000000000"

@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _check_supabase() -> None:
    """Run a trivial, time-bounded query against Supabase to prove
    connectivity/auth.

    Reuses `rag_pipeline.list_documents` (called as `rag_pipeline.<name>`,
    same module-qualified-attribute convention as
    rag_api/routes/documents.py, so tests can patch
    `rag_pipeline.list_documents` directly) rather than talking to the
    Supabase client directly - this is the same query nearly every other
    route in this service already runs, so no new table/permission is needed
    purely for this check, and it stays a single indexed lookup rather than
    an unbounded scan.

    Bounded to `READYZ_SUPABASE_TIMEOUT_SECONDS`: without a timeout, a
    Supabase instance that is merely slow (rather than erroring outright)
    would leave this call - and the request thread waiting on it - blocked
    for however long the underlying HTTP client's default timeout is, which
    can be far longer than callers of `/readyz` (the ALB target group health
    check) are willing to wait. `list_documents` itself takes no timeout
    parameter, and this route handler is a sync `def` already running in
    FastAPI's own threadpool, so the call is submitted to a fresh,
    single-use, single-worker `ThreadPoolExecutor` (created and torn down
    per call, not shared across requests - a shared pool would let one slow
    request's still-running probe thread starve every other concurrent
    `/readyz` request's own probe behind it in the same queue) and bounded
    via `Future.result(timeout=)`. `concurrent.futures.TimeoutError`
    propagates to `readyz()` below exactly like any other failure from
    `rag_pipeline.list_documents` itself - both are caught by the same
    broad `except Exception` there. The submitted call itself is not
    cancelled on timeout (the underlying HTTP client call has no cooperative
    cancellation hook); it's simply left to finish or fail on its own
    timeline in the background thread (the executor is shut down with
    `wait=False`, so tearing it down here doesn't block on that), and its
    result is discarded - acceptable here since this is a cheap,
    side-effect-free read.
    """
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="readyz-supabase-probe"
    )
    try:
        future = executor.submit(rag_pipeline.list_documents, _READYZ_PROBE_USER_ID)
        future.result(timeout=READYZ_SUPABASE_TIMEOUT_SECONDS)
    finally:
        executor.shutdown(wait=False)


@router.get("/readyz", dependencies=[Depends(require_readyz_rate_limit)])
def readyz(response: Response) -> dict[str, Any]:
    checks: dict[str, str] = {}
    healthy = True

    try:
        _check_supabase()
        checks["supabase"] = "ok"
    except Exception:  # noqa: BLE001 - deliberately broad: any failure
        # reaching/querying Supabase (including a `_check_supabase` timeout,
        # which raises `concurrent.futures.TimeoutError`, itself an
        # `Exception` subclass) means this task isn't ready, regardless of
        # the specific exception type. The exception's own message is never
        # included in the response body - it can embed connection details
        # (see rag_pipeline.supabase_client, which is built from
        # SUPABASE_URL/SUPABASE_SERVICE_KEY) that must never leak into an
        # unauthenticated response (this route, like /healthz, is
        # intentionally reachable without X-Internal-Api-Key so the ALB can
        # call it).
        healthy = False
        checks["supabase"] = "error"

    if not healthy:
        response.status_code = 503

    return {"status": "ok" if healthy else "degraded", "checks": checks}

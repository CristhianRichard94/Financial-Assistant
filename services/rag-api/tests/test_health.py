from __future__ import annotations

import time

from rag_api.routes import health


def test_healthz_returns_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_does_not_check_dependencies(client, mocker):
    """Regression test: /healthz must stay a bare liveness check, never
    touching rag_pipeline/Supabase, even if /readyz's dependency check is
    later broken or misconfigured to call the same code."""
    list_documents = mocker.patch("rag_pipeline.list_documents")

    response = client.get("/healthz")

    assert response.status_code == 200
    list_documents.assert_not_called()


def test_readyz_returns_200_when_supabase_is_reachable(client, mocker):
    mocker.patch("rag_pipeline.list_documents", return_value=[])

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["supabase"] == "ok"


def test_readyz_returns_503_when_supabase_is_unreachable(client, mocker):
    mocker.patch(
        "rag_pipeline.list_documents",
        side_effect=RuntimeError("connection string postgres://user:pass@host/db"),
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["supabase"] == "error"
    # The raw exception message (which can embed connection details) must
    # never leak into this unauthenticated response body.
    assert "postgres://user:pass@host/db" not in response.text


def test_readyz_does_not_require_internal_api_key(unauthenticated_client, mocker):
    mocker.patch("rag_pipeline.list_documents", return_value=[])

    response = unauthenticated_client.get("/readyz")

    assert response.status_code == 200


def test_readyz_returns_503_within_bounded_time_when_supabase_hangs(
    unauthenticated_client, mocker, monkeypatch
):
    """Regression test for the MED finding: a Supabase call that merely
    hangs (rather than erroring outright) must still be treated as
    not-ready, within a bounded time - not left to block on the underlying
    HTTP client's own (much longer) default timeout."""
    monkeypatch.setattr(health, "READYZ_SUPABASE_TIMEOUT_SECONDS", 0.2)

    def _hang(*args, **kwargs):
        time.sleep(2)
        return []

    mocker.patch("rag_pipeline.list_documents", side_effect=_hang)

    started = time.monotonic()
    response = unauthenticated_client.get("/readyz")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["supabase"] == "error"
    # Bounded well below the 2-second hang above - the probe's own 0.2s
    # timeout, not the hang itself, must determine how long this takes.
    assert elapsed < 1.5


def test_check_supabase_executor_is_module_level_not_recreated_per_call(mocker):
    """Regression test for issue #36: `_check_supabase` must reuse a
    bounded, module-level executor across calls, not create (and
    `shutdown(wait=False)`) a fresh `ThreadPoolExecutor` per call - a fresh
    per-call executor doesn't kill a truly hung worker thread, so threads
    accumulate unbounded during a sustained Supabase outage.
    """
    mocker.patch("rag_pipeline.list_documents", return_value=[])

    executor_before = health._SUPABASE_PROBE_EXECUTOR
    health._check_supabase()
    health._check_supabase()
    executor_after = health._SUPABASE_PROBE_EXECUTOR

    assert executor_before is executor_after
    assert isinstance(executor_before, health.concurrent.futures.ThreadPoolExecutor)


def test_readyz_rate_limits_after_threshold(unauthenticated_client, mocker, monkeypatch):
    """/readyz is unauthenticated by necessity (the ALB can't send
    X-Internal-Api-Key), so it must still be protected by a global,
    IP-agnostic rate limit - see the BLOCKING security finding this
    regression-tests."""
    monkeypatch.setenv("READYZ_RATE_LIMIT_PER_SECOND", "2")
    mocker.patch("rag_pipeline.list_documents", return_value=[])

    first = unauthenticated_client.get("/readyz")
    second = unauthenticated_client.get("/readyz")
    third = unauthenticated_client.get("/readyz")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Retry-After" in third.headers

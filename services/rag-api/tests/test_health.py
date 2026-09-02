from __future__ import annotations


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

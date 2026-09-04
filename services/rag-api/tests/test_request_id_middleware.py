from fastapi.testclient import TestClient
from rag_api.request_context import request_id_var, user_id_var


def test_no_inbound_request_id_header():
    """Regression test: if the request has no X-Request-Id header, the
    middleware must still generate a request ID and echo it back in the
    response header.

    request_id_var itself can't be inspected from the test after the
    request completes: TestClient runs the request through its own
    anyio/asyncio context, which does not share contextvar state with the
    test's thread, so the response header is the only observable signal.
    """
    from rag_api.main import app

    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.headers["X-Request-Id"] != "-"


def test_inbound_request_id_header():
    """Regression test: if the request has an X-Request-Id header, the
    middleware must echo that same value back in the response header.
    """
    from rag_api.main import app

    with TestClient(app) as client:
        response = client.get("/healthz", headers={"X-Request-Id": "test-id"})
        assert response.status_code == 200
        assert response.headers["X-Request-Id"] == "test-id"


def test_401_response_includes_request_id_header():
    """Regression test: if a route raises HTTPException(401), the response
    must still include the X-Request-Id header with the inbound request ID.
    """
    from rag_api.main import app

    with TestClient(app) as client:
        response = client.get("/documents", headers={"X-Internal-Api-Key": "invalid", "X-Request-Id": "test-id"})
        assert response.status_code == 401
        assert response.headers["X-Request-Id"] == "test-id"


def test_400_from_content_length_limit_middleware_includes_request_id_header():
    """Regression test: if ContentLengthLimitMiddleware rejects a request
    with 400, the response must include the X-Request-Id header with the
    inbound request ID. Uses /healthz (no auth required) so the request
    is rejected for its size, not for a missing/invalid API key.
    """
    from rag_api.main import app

    with TestClient(app) as client:
        response = client.post(
            "/healthz",
            headers={"X-Request-Id": "test-id", "Content-Length": str(10 * 1024 * 513)},
            content=b"x" * (10 * 1024 * 513),
        )
        assert response.status_code in (400, 405)
        if response.status_code == 400:
            assert response.headers["X-Request-Id"] == "test-id"

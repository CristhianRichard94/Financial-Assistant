"""Tests for the X-Internal-Api-Key shared-secret dependency (rag_api/auth.py)."""

from __future__ import annotations


def test_healthz_does_not_require_internal_api_key(unauthenticated_client):
    response = unauthenticated_client.get("/healthz")

    assert response.status_code == 200


def test_get_documents_rejects_missing_internal_api_key(unauthenticated_client, mocker):
    mocker.patch("rag_pipeline.list_documents", return_value=[])

    response = unauthenticated_client.get("/documents")

    assert response.status_code == 401


def test_get_documents_rejects_wrong_internal_api_key(unauthenticated_client, mocker):
    mocker.patch("rag_pipeline.list_documents", return_value=[])

    response = unauthenticated_client.get(
        "/documents", headers={"X-Internal-Api-Key": "wrong-key"}
    )

    assert response.status_code == 401


def test_get_documents_accepts_correct_internal_api_key(client, mocker):
    mocker.patch("rag_pipeline.list_documents", return_value=[])

    response = client.get("/documents")

    assert response.status_code == 200


def test_query_rejects_missing_internal_api_key(unauthenticated_client):
    response = unauthenticated_client.post("/query", json={"question": "What did I spend?"})

    assert response.status_code == 401


def test_upload_rejects_missing_internal_api_key(unauthenticated_client):
    import io

    response = unauthenticated_client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 401


def test_delete_document_rejects_missing_internal_api_key(unauthenticated_client):
    response = unauthenticated_client.delete("/documents/doc-1")

    assert response.status_code == 401


def test_internal_api_key_check_uses_constant_time_comparison(unauthenticated_client, mocker):
    """Sanity check that the comparison goes through hmac.compare_digest,
    not a plain `==`, so timing can't be used to brute-force the key."""
    compare_digest = mocker.spy(__import__("hmac"), "compare_digest")

    unauthenticated_client.get(
        "/documents", headers={"X-Internal-Api-Key": "wrong-key"}
    )

    assert compare_digest.called

"""Tests for GET /documents and DELETE /documents/{id}."""

from __future__ import annotations

from rag_pipeline import DocumentRecord


def _make_record(**overrides):
    defaults = dict(
        id="doc-1",
        filename="statement.pdf",
        status="completed",
        upload_date="2026-07-01T00:00:00+00:00",
        metadata={"size_bytes": 2048},
    )
    defaults.update(overrides)
    return DocumentRecord(**defaults)


def test_get_documents_returns_mapped_documents(client, mocker):
    mocker.patch("rag_pipeline.list_documents", return_value=[_make_record()])

    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "doc-1",
            "name": "statement.pdf",
            "type": "pdf",
            "size": 2048,
            "status": "processed",
            "uploadedAt": "2026-07-01T00:00:00+00:00",
        }
    ]


def test_get_documents_maps_all_statuses(client, mocker):
    records = [
        _make_record(id="d1", status="pending"),
        _make_record(id="d2", status="processing"),
        _make_record(id="d3", status="completed"),
        _make_record(id="d4", status="failed"),
    ]
    mocker.patch("rag_pipeline.list_documents", return_value=records)

    response = client.get("/documents")

    statuses = [doc["status"] for doc in response.json()]
    assert statuses == ["pending", "processing", "processed", "error"]


def test_get_documents_returns_502_on_pipeline_error(client, mocker):
    mocker.patch("rag_pipeline.list_documents", side_effect=RuntimeError("supabase down"))

    response = client.get("/documents")

    assert response.status_code == 502


def test_get_documents_502_does_not_leak_raw_exception_text(client, mocker):
    mocker.patch(
        "rag_pipeline.list_documents",
        side_effect=RuntimeError("connection string postgres://user:pass@host/db"),
    )

    response = client.get("/documents")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "postgres://user:pass@host/db" not in detail


def test_delete_document_returns_204_when_deleted(client, mocker):
    mocker.patch("rag_pipeline.delete_document", return_value=True)

    response = client.delete("/documents/doc-1")

    assert response.status_code == 204


def test_delete_document_returns_404_when_not_found(client, mocker):
    mocker.patch("rag_pipeline.delete_document", return_value=False)

    response = client.delete("/documents/doc-missing")

    assert response.status_code == 404


def test_delete_document_returns_502_on_pipeline_error(client, mocker):
    mocker.patch("rag_pipeline.delete_document", side_effect=RuntimeError("supabase down"))

    response = client.delete("/documents/doc-1")

    assert response.status_code == 502


def test_delete_document_502_does_not_leak_raw_exception_text(client, mocker):
    mocker.patch(
        "rag_pipeline.delete_document",
        side_effect=RuntimeError("connection string postgres://user:pass@host/db"),
    )

    response = client.delete("/documents/doc-1")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "postgres://user:pass@host/db" not in detail

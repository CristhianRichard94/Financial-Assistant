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
            "errorMessage": None,
        }
    ]


def test_get_documents_scopes_to_the_requesting_user(client, user_id, mocker):
    list_documents = mocker.patch("rag_pipeline.list_documents", return_value=[])

    client.get("/documents")

    list_documents.assert_called_once_with(user_id)


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


def test_upload_document_background_ingestion_logs_request_id(client, mocker, caplog):
    """Regression test: the background ingestion task must log under the
    same request_id the inbound request carried, even though it runs after
    the response has been sent. JsonLogFormatter reads request_id_var at
    log-emit time rather than storing it on the record, so we snapshot the
    contextvar onto each record via a logging.Filter at emit time - reading
    it back from caplog's records after the request completes (when the
    contextvar has already been reset) would silently see the wrong value.
    """
    import logging

    request_id = "request-123"
    mocker.patch("rag_pipeline.create_pending_document", return_value="doc-1")
    mocker.patch("rag_api.routes.documents.load_pipeline_settings", return_value=object())
    mocker.patch("rag_pipeline.process_document", side_effect=RuntimeError("boom"))
    mocker.patch("rag_pipeline.mark_document_failed", return_value=None)

    from rag_api.request_context import request_id_var

    def _snapshot_request_id(record):
        record.captured_request_id = request_id_var.get()
        return True

    snapshot_filter = logging.Filter()
    snapshot_filter.filter = _snapshot_request_id
    with caplog.at_level("INFO"):
        caplog.handler.addFilter(snapshot_filter)
        try:
            response = client.post(
                "/upload",
                headers={"X-Request-ID": request_id},
                files={"file": ("statement.pdf", b"%PDF-1.4", "application/pdf")},
            )
        finally:
            caplog.handler.removeFilter(snapshot_filter)

    assert response.status_code == 201
    ingestion_logs = [
        record for record in caplog.records if "ingestion" in record.getMessage().lower()
    ]
    assert ingestion_logs
    assert all(record.captured_request_id == request_id for record in ingestion_logs)


def test_delete_document_returns_204_when_deleted(client, mocker):
    mocker.patch("rag_pipeline.delete_document", return_value=True)

    response = client.delete("/documents/doc-1")

    assert response.status_code == 204


def test_delete_document_scopes_to_the_requesting_user(client, user_id, mocker):
    delete_document = mocker.patch("rag_pipeline.delete_document", return_value=True)

    client.delete("/documents/doc-1")

    delete_document.assert_called_once_with("doc-1", user_id)


def test_delete_document_returns_404_when_not_found(client, mocker):
    mocker.patch("rag_pipeline.delete_document", return_value=False)

    response = client.delete("/documents/doc-missing")

    assert response.status_code == 404


def test_delete_document_returns_404_when_owned_by_another_user(
    client, user_id, other_user_id, mocker
):
    """A document that exists but belongs to a different user must return
    the same 404 as a document that doesn't exist at all - never leak that
    the id belongs to someone else."""

    def fake_delete_document(document_id, requesting_user_id):
        # Simulates a `documents` row owned by `other_user_id`: only a
        # delete request asserting that same user id would ever succeed.
        return requesting_user_id == other_user_id

    mocker.patch("rag_pipeline.delete_document", side_effect=fake_delete_document)

    # `client` sends `user_id`, not `other_user_id` - the actual owner.
    response = client.delete("/documents/doc-1")

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

"""Tests for POST /upload."""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException

from rag_api.config import RagApiSettings
from rag_api.routes.documents import _sanitize_filename, _stream_multipart_file


def test_upload_document_returns_201_with_pending_document(client, mocker):
    mocker.patch("rag_pipeline.create_pending_document", return_value="new-doc-id")
    mocker.patch("rag_pipeline.process_document")  # background task, not exercised here

    response = client.post(
        "/upload",
        files={
            "file": (
                "statement.pdf",
                io.BytesIO(b"%PDF-1.4 fake pdf content"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "new-doc-id"
    assert body["name"] == "statement.pdf"
    assert body["type"] == "pdf"
    assert body["status"] == "pending"
    assert body["size"] > 0
    assert "uploadedAt" in body


def test_upload_document_accepts_csv(client, mocker):
    mocker.patch("rag_pipeline.create_pending_document", return_value="new-doc-id")
    mocker.patch("rag_pipeline.process_document")

    response = client.post(
        "/upload",
        files={"file": ("transactions.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 201
    assert response.json()["type"] == "csv"


def test_upload_document_rejects_bad_extension(client, mocker):
    create_mock = mocker.patch("rag_pipeline.create_pending_document")

    response = client.post(
        "/upload",
        files={"file": ("malware.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )

    assert response.status_code == 400
    create_mock.assert_not_called()


def test_upload_document_rejects_oversized_file(client, mocker):
    create_mock = mocker.patch("rag_pipeline.create_pending_document")
    oversized_content = b"0" * (10 * 1024 * 1024 + 1)

    response = client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(oversized_content), "text/csv")},
    )

    assert response.status_code == 400
    create_mock.assert_not_called()


def test_upload_document_returns_502_on_pipeline_error(client, mocker):
    mocker.patch(
        "rag_pipeline.create_pending_document", side_effect=RuntimeError("supabase down")
    )

    response = client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 502


def test_upload_document_502_does_not_leak_raw_exception_text(client, mocker):
    mocker.patch(
        "rag_pipeline.create_pending_document",
        side_effect=RuntimeError("postgres://user:pass@host/db is unreachable"),
    )

    response = client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "postgres://user:pass@host/db" not in detail


def test_upload_document_rejects_fake_pdf_missing_magic_bytes(client, mocker):
    create_mock = mocker.patch("rag_pipeline.create_pending_document")

    response = client.post(
        "/upload",
        files={
            "file": (
                "not_really_a_pdf.pdf",
                io.BytesIO(b"this is just plain text, not a pdf"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 400
    create_mock.assert_not_called()


def test_upload_document_sanitizes_path_traversal_filename(client, mocker):
    mocker.patch("rag_pipeline.create_pending_document", return_value="new-doc-id")
    mocker.patch("rag_pipeline.process_document")

    response = client.post(
        "/upload",
        files={
            "file": (
                "../../etc/passed.pdf",
                io.BytesIO(b"%PDF-1.4 fake pdf content"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "passed.pdf"
    assert ".." not in response.json()["name"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passed.pdf", "passed.pdf"),
        ("..\\..\\windows\\evil.pdf", "evil.pdf"),
        ("a/b/c.pdf", "c.pdf"),
        ("normal.pdf", "normal.pdf"),
        ("..", "unnamed"),
        (".", "unnamed"),
        ("", "unnamed"),
        ("/etc/passwd.pdf", "passwd.pdf"),
    ],
)
def test_sanitize_filename_strips_path_components(raw, expected):
    assert _sanitize_filename(raw) == expected


class _FakeBodyStream:
    """Stand-in for FastAPI's `Request.stream()` that serves pre-chunked
    bytes from an in-memory list and records how many chunks were ever
    pulled, so tests can prove `_stream_multipart_file` aborts mid-parse -
    without ever reading the rest of the underlying network stream - instead
    of buffering the whole request body first."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.chunks_yielded = 0

    def __aiter__(self) -> "_FakeBodyStream":
        return self

    async def __anext__(self) -> bytes:
        if not self._chunks:
            raise StopAsyncIteration
        chunk = self._chunks.pop(0)
        self.chunks_yielded += 1
        return chunk


def _make_settings(max_upload_bytes: int = 10 * 1024 * 1024) -> RagApiSettings:
    return RagApiSettings(
        anthropic_api_key="sk-ant-test",
        internal_api_key="test-internal-api-key",
        max_upload_bytes=max_upload_bytes,
    )


_TEST_BOUNDARY = "TESTBOUNDARY"
_TEST_HEADERS = {"content-type": f"multipart/form-data; boundary={_TEST_BOUNDARY}"}


def _file_part_header(filename: str, content_type: str = "text/csv") -> bytes:
    """The header portion of a single "file" multipart part, from the
    opening boundary line through the blank line that precedes its body."""
    return (
        f"--{_TEST_BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode()


_TEST_TRAILER = f"\r\n--{_TEST_BOUNDARY}--\r\n".encode()


def test_stream_multipart_file_returns_full_content_within_limit():
    stream = _FakeBodyStream(
        [_file_part_header("statement.csv"), b"a,b\n1,2\n", _TEST_TRAILER]
    )

    filename, contents = asyncio.run(
        _stream_multipart_file(_TEST_HEADERS, stream, _make_settings())
    )

    assert filename == "statement.csv"
    assert contents == b"a,b\n1,2\n"


def test_stream_multipart_file_aborts_before_reading_all_chunks():
    """A file whose first content chunk already exceeds the limit must be
    rejected without the underlying body stream ever being asked for the
    remaining chunks - proving the check happens incrementally, as bytes
    are read off the (simulated) network, not after buffering the entire
    request body first."""
    stream = _FakeBodyStream(
        [
            _file_part_header("big.csv"),
            b"x" * 20,  # already exceeds max_upload_bytes=10 on its own
            b"y" * 20,
            _TEST_TRAILER,
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            _stream_multipart_file(_TEST_HEADERS, stream, _make_settings(max_upload_bytes=10))
        )

    assert exc_info.value.status_code == 400
    # Only the header chunk and the first (oversized) content chunk should
    # ever have been pulled from the stream - the second content chunk and
    # the closing boundary must never be read.
    assert stream.chunks_yielded == 2


def test_stream_multipart_file_rejects_bad_extension_before_reading_content():
    """An unsupported extension must be rejected as soon as the part's
    headers are parsed - before any of its (potentially huge) content is
    ever read off the stream."""
    stream = _FakeBodyStream(
        [_file_part_header("malware.exe", content_type="application/octet-stream"), b"x" * 1000, _TEST_TRAILER]
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_stream_multipart_file(_TEST_HEADERS, stream, _make_settings()))

    assert exc_info.value.status_code == 400
    # Only the header chunk should have been read - content was never
    # touched because the extension check runs before any part_data.
    assert stream.chunks_yielded == 1


def test_upload_background_ingestion_marks_failed_on_early_exception(client, mocker):
    """If the pipeline raises before it ever updates the document row's
    status (e.g. settings loading or the Supabase client itself failing),
    the background task must still mark the document "failed" via the
    mark_document_failed fallback, instead of leaving it stuck "pending"
    forever."""
    mocker.patch("rag_pipeline.create_pending_document", return_value="new-doc-id")
    mocker.patch(
        "rag_pipeline.process_document",
        side_effect=RuntimeError("boom before any status update"),
    )
    mark_failed_mock = mocker.patch("rag_pipeline.mark_document_failed")

    response = client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 201
    mark_failed_mock.assert_called_once_with("new-doc-id")


def test_upload_background_ingestion_tolerates_mark_failed_error(client, mocker):
    """Even if the best-effort mark_document_failed fallback itself raises
    (e.g. Supabase is completely unreachable), the background task must not
    crash or propagate that error - it's already best-effort."""
    mocker.patch("rag_pipeline.create_pending_document", return_value="new-doc-id")
    mocker.patch("rag_pipeline.process_document", side_effect=RuntimeError("boom"))
    mocker.patch(
        "rag_pipeline.mark_document_failed",
        side_effect=RuntimeError("supabase also unreachable"),
    )

    response = client.post(
        "/upload",
        files={"file": ("statement.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )

    assert response.status_code == 201

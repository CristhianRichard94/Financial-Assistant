"""Document listing, upload, and deletion routes.

All calls into rag_pipeline are made as `rag_pipeline.<name>(...)` (module-
qualified attribute access) rather than `from rag_pipeline import <name>`, so
that tests can patch `rag_pipeline.<name>` directly and have it take effect
here without needing to know this module's internal import structure.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import python_multipart as multipart
import rag_pipeline
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from rag_pipeline.config import load_settings as load_pipeline_settings

from rag_api.auth import require_internal_api_key, require_user_id
from rag_api.config import RagApiSettings, load_rag_api_settings
from rag_api.schemas import DocumentOut
from rag_api.status_mapping import document_record_to_out, infer_document_type

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_internal_api_key)])

# PDFs always start with this magic string. Used as a lightweight sniff so a
# payload merely renamed to ".pdf" doesn't sail through undetected. CSV and
# plain-text files have no reliable magic number to check, so extension-based
# validation remains the practical limit there; this is intentionally scoped
# to PDF only, not a general-purpose content-type sniffer.
_PDF_MAGIC_BYTES = b"%PDF-"


def _sanitize_filename(filename: str) -> str:
    """Reduce a client-supplied filename to a safe basename for storage/display.

    Client-supplied filenames are persisted to `documents.filename` and
    echoed back verbatim in API responses (`DocumentOut.name`), so strip any
    path components defensively (e.g. "../../etc/passwd.pdf" -> "passwd.pdf")
    even though this implementation never uses the raw filename as a
    filesystem path anywhere (uploads are written to a `NamedTemporaryFile`,
    reusing only the extension). Handles both POSIX and Windows-style path
    separators since the uploading client's OS is unknown.
    """
    candidate = filename.replace("\\", "/").split("/")[-1].strip()
    if not candidate or candidate in {".", ".."}:
        return "unnamed"
    return candidate


def _validate_extension(filename: str, settings: RagApiSettings) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed types: {allowed}",
        )


def _validate_pdf_magic_bytes(filename: str, contents: bytes) -> None:
    if Path(filename).suffix.lower() == ".pdf" and not contents.startswith(_PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File does not appear to be a valid PDF.",
        )


class _UploadTooLargeError(Exception):
    """Internal sentinel raised by `_stream_multipart_file`'s parser
    callbacks the instant the request body crosses the configured size
    limit, so the surrounding loop stops pulling further chunks off the
    network stream immediately. Caught and translated into an HTTPException
    inside `_stream_multipart_file` itself - it must never escape that
    function.
    """


# Generous allowance, on top of the actual file content limit, for the
# multipart boundary markers/part headers/any other small form fields the
# request happens to include. The file content itself is still bounded to
# exactly `settings.max_upload_bytes` by the per-file-part check in
# `_stream_multipart_file`; this is a coarser backstop bounding the *entire*
# request body, so a client can't get around the file-part check by padding
# the request with bytes outside of the "file" field, and so the bound
# holds even when Content-Length is absent or understated.
_MULTIPART_OVERHEAD_ALLOWANCE_BYTES = 64 * 1024


@dataclass
class _FileFieldState:
    """Tracks the "file" field as it's discovered/consumed across multipart
    parser callbacks."""

    is_current_part_file: bool = False
    filename: str | None = None
    buffer: bytearray = field(default_factory=bytearray)


@dataclass
class _HeaderState:
    """Accumulates the current part header name/value across the (possibly
    many) `on_header_field`/`on_header_value` callback invocations that
    together make up a single header line."""

    name: bytes = b""
    value: bytes = b""
    disposition: bytes = b""


async def _stream_multipart_file(
    headers: Mapping[str, str],
    body_stream: AsyncIterator[bytes],
    settings: RagApiSettings,
) -> tuple[str, bytes]:
    """Parse a multipart/form-data body directly off `body_stream`, extracting
    the "file" field's (sanitized, extension-validated) filename and
    contents, and abort the instant either the file part or the request
    body as a whole crosses the configured size limit.

    This deliberately bypasses FastAPI's `UploadFile`/`File(...)`: Starlette's
    own `MultiPartParser` (which backs `UploadFile`) only enforces
    `max_part_size` on inline form *fields*, not file parts - for file parts
    it spools the entire body to a `SpooledTemporaryFile` with no size limit
    at all, regardless of Content-Length or any check the route handler
    tries to run afterwards (see round-2 security finding). By reading the
    raw ASGI body stream ourselves and feeding python-multipart's low-level
    streaming parser directly, we control buffering from the very first
    byte and can abort mid-parse - before any further bytes for this
    request are even read off the socket, let alone spooled to disk or
    memory.
    """
    content_type = headers.get("content-type", "")
    _, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if not boundary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request must be multipart/form-data with a valid boundary.",
        )

    file_state = _FileFieldState()
    header_state = _HeaderState()

    def on_part_begin() -> None:
        file_state.is_current_part_file = False

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_state.name += data[start:end]

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_state.value += data[start:end]

    def on_header_end() -> None:
        if header_state.name.lower() == b"content-disposition":
            header_state.disposition = header_state.value
        header_state.name = b""
        header_state.value = b""

    def on_headers_finished() -> None:
        _, options = parse_options_header(header_state.disposition)
        header_state.disposition = b""
        field_name = options.get(b"name", b"").decode("latin-1")
        if field_name != "file" or b"filename" not in options:
            return
        raw_filename = options[b"filename"].decode("latin-1")
        filename = _sanitize_filename(raw_filename or "unnamed")
        # Validated as soon as headers for the file part are parsed - i.e.
        # before a single byte of the (potentially oversized) file content
        # itself has been read off the stream.
        _validate_extension(filename, settings)
        file_state.is_current_part_file = True
        file_state.filename = filename

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if not file_state.is_current_part_file:
            return
        file_state.buffer.extend(data[start:end])
        if len(file_state.buffer) > settings.max_upload_bytes:
            raise _UploadTooLargeError

    parser = multipart.MultipartParser(
        boundary,
        {
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
        },
    )

    total_body_cap = settings.max_upload_bytes + _MULTIPART_OVERHEAD_ALLOWANCE_BYTES
    total_bytes_seen = 0
    try:
        async for chunk in body_stream:
            if not chunk:
                continue
            total_bytes_seen += len(chunk)
            if total_bytes_seen > total_body_cap:
                raise _UploadTooLargeError
            parser.write(chunk)
        parser.finalize()
    except _UploadTooLargeError:
        max_mb = settings.max_upload_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {max_mb:.0f}MB size limit",
        ) from None
    except MultipartParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed multipart upload body.",
        ) from exc

    if file_state.filename is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided")
    return file_state.filename, bytes(file_state.buffer)


def _run_ingestion(document_id: str, tmp_path: str, user_id: str) -> None:
    """Background task: parse/chunk/embed/store the uploaded file.

    `process_document` marks its own document row "failed" for failures that
    happen after its first Supabase status update ("processing"). This
    wrapper adds a best-effort fallback for failures that happen *before*
    that point (e.g. `load_pipeline_settings()` raising on a missing env
    var, or the Supabase client construction/first call itself failing):
    without it, the row would stay "pending" forever with no failure ever
    surfaced, since the frontend polls GET /documents specifically while
    status is "pending"/"processing".
    """
    try:
        pipeline_settings = load_pipeline_settings()
        rag_pipeline.process_document(
            document_id, tmp_path, user_id, settings=pipeline_settings
        )
    except Exception:
        logger.exception("Background ingestion failed for document %s", document_id)
        try:
            rag_pipeline.mark_document_failed(document_id)
        except Exception:
            # Swallow: a secondary failure here must not crash the
            # background task or mask the original ingestion error above,
            # which is already logged. There's no better fallback than
            # logging if even this best-effort update fails.
            logger.exception(
                "Failed to mark document %s as failed after an ingestion error",
                document_id,
            )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/documents", response_model=list[DocumentOut])
def get_documents(user_id: str = Depends(require_user_id)) -> list[DocumentOut]:
    try:
        records = rag_pipeline.list_documents(user_id)
    except Exception:
        logger.exception("Failed to list documents")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to list documents.",
        ) from None
    return [document_record_to_out(record) for record in records]


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_user_id),
) -> DocumentOut:
    # Deliberately does not declare `file: UploadFile = File(...)` - see
    # `_stream_multipart_file`'s docstring for why. The request body is
    # parsed manually, straight off `request.stream()`, so this handler
    # controls buffering from the first byte instead of relying on
    # Starlette's own (unbounded, for file parts) multipart parser.
    settings = load_rag_api_settings()
    filename, contents = await _stream_multipart_file(request.headers, request.stream(), settings)
    _validate_pdf_magic_bytes(filename, contents)

    try:
        document_id = rag_pipeline.create_pending_document(
            filename, user_id, metadata={"size_bytes": len(contents)}
        )
    except Exception:
        logger.exception("Failed to create document record")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create document record.",
        ) from None

    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(contents)
        tmp_path = tmp_file.name

    background_tasks.add_task(_run_ingestion, document_id, tmp_path, user_id)

    return DocumentOut(
        id=document_id,
        name=filename,
        type=infer_document_type(filename),
        size=len(contents),
        status="pending",
        uploaded_at=datetime.now(timezone.utc).isoformat(),
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(document_id: str, user_id: str = Depends(require_user_id)) -> None:
    try:
        deleted = rag_pipeline.delete_document(document_id, user_id)
    except Exception:
        logger.exception("Failed to delete document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to delete document.",
        ) from None
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

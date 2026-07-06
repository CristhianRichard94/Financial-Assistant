"""Mapping between rag_pipeline's `documents.status`/filename conventions and
the frontend-facing `DocumentOut` shape."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rag_pipeline import DocumentRecord

from rag_api.schemas import DocumentOut, DocumentStatusOut, DocumentTypeOut

# rag_pipeline's `documents.status` values -> the frontend's `Document["status"]`
# values (see artifacts/finsight/src/lib/store.ts). The pipeline's "completed"
# maps to the frontend's "processed", and "failed" maps to "error"; the rest
# are shared verbatim.
STATUS_MAP: dict[str, DocumentStatusOut] = {
    "pending": "pending",
    "processing": "processing",
    "completed": "processed",
    "failed": "error",
}

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def infer_document_type(filename: str) -> DocumentTypeOut:
    """Infer the frontend-facing document type from a filename's extension."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".csv":
        return "csv"
    return "image"


def _size_bytes_from_metadata(metadata: dict[str, Any]) -> int:
    size = metadata.get("size_bytes")
    return int(size) if isinstance(size, (int, float)) else 0


def document_record_to_out(record: DocumentRecord) -> DocumentOut:
    """Convert a rag_pipeline `DocumentRecord` into the frontend-facing shape."""
    status = STATUS_MAP.get(record.status, "error")
    return DocumentOut(
        id=record.id,
        name=record.filename,
        type=infer_document_type(record.filename),
        size=_size_bytes_from_metadata(record.metadata),
        status=status,
        uploaded_at=record.upload_date,
    )

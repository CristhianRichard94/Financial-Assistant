"""Read/delete access to the `documents` table (listing, lookup, deletion).

Ingestion itself (creating and processing rows) lives in `ingest.py`; this
module covers the rest of the CRUD surface an HTTP layer needs on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag_pipeline.config import Settings, load_settings
from rag_pipeline.supabase_client import get_supabase_client


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    filename: str
    status: str
    upload_date: str
    metadata: dict[str, Any]


def _row_to_record(row: dict[str, Any]) -> DocumentRecord:
    return DocumentRecord(
        id=row["id"],
        filename=row["filename"],
        status=row["status"],
        upload_date=row["upload_date"],
        metadata=row.get("metadata") or {},
    )


def list_documents(settings: Settings | None = None) -> list[DocumentRecord]:
    """Return all documents, most recently uploaded first."""
    settings = settings or load_settings()
    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    response = (
        supabase.table("documents")
        .select("*")
        .order("upload_date", desc=True)
        .execute()
    )
    return [_row_to_record(row) for row in response.data]


def get_document(document_id: str, settings: Settings | None = None) -> DocumentRecord | None:
    """Return a single document by id, or None if it doesn't exist."""
    settings = settings or load_settings()
    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    response = (
        supabase.table("documents")
        .select("*")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    return _row_to_record(response.data[0])


def delete_document(document_id: str, settings: Settings | None = None) -> bool:
    """Delete a document by id. Returns True if a row was deleted, False otherwise.

    Deleting a `documents` row cascades to its `document_chunks` rows (see
    `on delete cascade` in sql/003_create_document_chunks_table.sql).
    """
    settings = settings or load_settings()
    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    response = supabase.table("documents").delete().eq("id", document_id).execute()
    return len(response.data) > 0

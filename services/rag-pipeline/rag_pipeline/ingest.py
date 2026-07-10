"""Document ingestion: parse -> chunk -> embed -> store in Supabase."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_pipeline.chunking import chunk_text
from rag_pipeline.config import EMBEDDING_DIMENSIONS, Settings, load_settings
from rag_pipeline.embeddings import embed_texts
from rag_pipeline.parsing import parse_document
from rag_pipeline.supabase_client import get_supabase_client


@dataclass(frozen=True)
class IngestResult:
    document_id: str
    filename: str
    chunk_count: int
    embedding_dimensions: int


def create_pending_document(
    filename: str,
    user_id: str,
    metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> str:
    """Insert a `documents` row owned by `user_id` and return its new id.

    Status is left unset so the table's own default (`'pending'`, see
    sql/002_create_documents_table.sql) applies. This is split out from
    `process_document` so callers (e.g. an HTTP upload endpoint) can create
    the row and respond to the client immediately, then process the file
    asynchronously.
    """
    settings = settings or load_settings()
    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    document_row = (
        supabase.table("documents")
        .insert(
            {
                "filename": filename,
                "user_id": user_id,
                "metadata": metadata or {},
            }
        )
        .execute()
    )
    return document_row.data[0]["id"]


def process_document(
    document_id: str,
    path: str | Path,
    user_id: str,
    settings: Settings | None = None,
) -> IngestResult:
    """Parse, chunk, embed, and store a local file for an existing document row.

    Steps:
    1. Set the `documents` row's status to "processing".
    2. Parse the file into raw text and split it into overlapping token chunks.
    3. Embed all chunks in one batched OpenAI request.
    4. Batch-insert all chunks into `document_chunks`.
    5. Mark the document "completed" (or "failed" if any step above raised).

    Raises ValueError if the file type is unsupported or the file has no
    extractable text (e.g. an empty CSV or an image-only PDF), and re-raises
    any underlying Supabase/OpenAI errors after marking the document failed.
    """
    settings = settings or load_settings()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)

    supabase.table("documents").update({"status": "processing"}).eq(
        "id", document_id
    ).execute()

    try:
        raw_text = parse_document(path)
        if not raw_text:
            raise ValueError(f"No extractable text found in {path}")

        chunks = chunk_text(raw_text)
        if not chunks:
            raise ValueError(f"Parsed text from {path} produced zero chunks")

        embeddings = embed_texts([chunk.text for chunk in chunks], settings.openai_api_key)

        chunk_rows = [
            {
                "document_id": document_id,
                "user_id": user_id,
                "chunk_text": chunk.text,
                "chunk_index": chunk.index,
                "embedding": embedding,
                "metadata": {"token_count": chunk.token_count},
            }
            for chunk, embedding in zip(chunks, embeddings)
        ]
        supabase.table("document_chunks").insert(chunk_rows).execute()

        supabase.table("documents").update({"status": "completed"}).eq(
            "id", document_id
        ).execute()

        return IngestResult(
            document_id=document_id,
            filename=path.name,
            chunk_count=len(chunk_rows),
            embedding_dimensions=EMBEDDING_DIMENSIONS,
        )
    except Exception:
        supabase.table("documents").update({"status": "failed"}).eq(
            "id", document_id
        ).execute()
        raise


def mark_document_failed(document_id: str, settings: Settings | None = None) -> None:
    """Best-effort: set a `documents` row's status to "failed".

    `process_document` already marks its own row "failed" for failures that
    occur after its first Supabase status update ("processing"). This
    function exists as a fallback for callers (e.g. the HTTP layer's
    background task in rag_api) that need to mark a document failed even
    when the failure happened *before* `process_document` got far enough to
    do that itself (e.g. `load_settings()` raising on a missing env var, or
    the Supabase client construction/first call itself failing). It loads
    its own settings/client independently rather than reusing anything the
    caller may have already tried to build, since that's exactly what may
    have failed.

    Raises if the update itself fails (e.g. Supabase is unreachable) -
    callers that want this to be fully best-effort should catch and log,
    not let a secondary failure here mask the original ingestion error.
    """
    settings = settings or load_settings()
    supabase = get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    supabase.table("documents").update({"status": "failed"}).eq(
        "id", document_id
    ).execute()


def ingest_document(
    path: str | Path,
    user_id: str,
    metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> IngestResult:
    """Ingest a single local PDF or CSV file into Supabase, end to end, owned
    by `user_id`.

    Thin wrapper around `create_pending_document` + `process_document`, kept
    for backwards compatibility with existing callers (e.g.
    scripts/test_ingest_and_query.py) that expect one call to do everything
    synchronously.
    """
    settings = settings or load_settings()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    document_id = create_pending_document(
        path.name, user_id, metadata=metadata, settings=settings
    )
    return process_document(document_id, path, user_id, settings=settings)

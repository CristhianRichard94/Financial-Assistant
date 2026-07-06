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


def ingest_document(
    path: str | Path,
    metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> IngestResult:
    """Ingest a single local PDF or CSV file into Supabase.

    Steps:
    1. Insert a `documents` row (status="processing").
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

    document_row = (
        supabase.table("documents")
        .insert(
            {
                "filename": path.name,
                "status": "processing",
                "metadata": metadata or {},
            }
        )
        .execute()
    )
    document_id = document_row.data[0]["id"]

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

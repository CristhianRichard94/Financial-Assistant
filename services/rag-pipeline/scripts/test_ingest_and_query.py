#!/usr/bin/env python3
"""End-to-end sanity check for the RAG pipeline.

Ingests the sample PDF and CSV under sample_data/, runs a similarity search
against them, and prints enough detail (chunk counts, embedding
dimensionality, top-k results with scores) for a human to eyeball whether
retrieval quality looks reasonable.

Requires real credentials (Supabase project with the sql/ migrations already
applied, plus an OpenAI API key) — see ../.env.example. If they're missing,
this prints a clear message instead of a raw traceback.

Usage:
    pip install -e .
    python scripts/test_ingest_and_query.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this script directly (`python scripts/test_ingest_and_query.py`)
# without requiring the package to already be on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag_pipeline.config import MissingEnvironmentVariable, load_settings
from rag_pipeline.ingest import ingest_document
from rag_pipeline.search import search

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
SAMPLE_PDF = SAMPLE_DIR / "sample_budget_guide.pdf"
SAMPLE_CSV = SAMPLE_DIR / "sample_transactions.csv"

TEST_QUERY = "How should I split my income between needs, wants, and savings?"
TOP_K = 5


def main() -> int:
    try:
        settings = load_settings()
    except MissingEnvironmentVariable as error:
        print("Cannot run the RAG pipeline test script: missing configuration.\n")
        print(f"  {error}\n")
        print(
            "Set SUPABASE_URL, SUPABASE_SERVICE_KEY, and OPENAI_API_KEY "
            "(see services/rag-pipeline/.env.example) and try again."
        )
        return 1

    for path in (SAMPLE_PDF, SAMPLE_CSV):
        if not path.exists():
            print(f"Sample file not found: {path}")
            print(
                "Regenerate it with 'python scripts/generate_sample_pdf.py' "
                "(PDF) or restore sample_data/sample_transactions.csv from git."
            )
            return 1

    print("=== Ingesting sample documents ===")
    total_chunks = 0
    embedding_dimensions = None
    for path in (SAMPLE_PDF, SAMPLE_CSV):
        try:
            result = ingest_document(path, settings=settings)
        except Exception as error:  # noqa: BLE001 - surface any failure clearly
            print(f"Failed to ingest {path.name}: {error}")
            return 1
        print(
            f"  {result.filename}: document_id={result.document_id} "
            f"chunks={result.chunk_count} embedding_dimensions={result.embedding_dimensions}"
        )
        total_chunks += result.chunk_count
        embedding_dimensions = result.embedding_dimensions

    print()
    print(f"Total chunks inserted: {total_chunks}")
    print(f"Embedding dimensionality: {embedding_dimensions}")
    if embedding_dimensions != 1536:
        print(
            f"WARNING: expected 1536 dimensions for text-embedding-3-small, "
            f"got {embedding_dimensions}."
        )

    print()
    print(f'=== Query: "{TEST_QUERY}" ===')
    try:
        results = search(TEST_QUERY, k=TOP_K, settings=settings)
    except Exception as error:  # noqa: BLE001
        print(f"Search failed: {error}")
        return 1

    if not results:
        print("No results returned. Did the SQL migrations run correctly?")
        return 1

    for rank, item in enumerate(results, start=1):
        preview = item.chunk_text.replace("\n", " ")
        if len(preview) > 160:
            preview = preview[:160] + "..."
        print(f"\n[{rank}] similarity={item.similarity:.4f} file={item.filename}")
        print(f"    metadata={item.chunk_metadata}")
        print(f"    text: {preview}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

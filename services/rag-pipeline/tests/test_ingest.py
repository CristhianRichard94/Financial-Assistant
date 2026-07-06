"""Tests for rag_pipeline.ingest: create_pending_document, process_document,
and the ingest_document wrapper."""

from __future__ import annotations

import pytest

from rag_pipeline.ingest import (
    create_pending_document,
    ingest_document,
    mark_document_failed,
    process_document,
)


def test_create_pending_document_inserts_row_with_metadata(fake_supabase, fake_settings):
    document_id = create_pending_document(
        "statement.pdf", metadata={"size_bytes": 1234}, settings=fake_settings
    )

    rows = fake_supabase.tables["documents"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == document_id
    assert row["filename"] == "statement.pdf"
    assert row["metadata"] == {"size_bytes": 1234}
    # Status is left for the table's own default ("pending") to apply.
    assert row["status"] == "pending"


def test_create_pending_document_defaults_metadata_to_empty_dict(
    fake_supabase, fake_settings
):
    create_pending_document("no_metadata.csv", settings=fake_settings)

    row = fake_supabase.tables["documents"][0]
    assert row["metadata"] == {}


def test_process_document_marks_completed_on_success(
    fake_supabase, fake_settings, fake_embeddings, tmp_path
):
    document_id = create_pending_document("statement.csv", settings=fake_settings)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text("description,amount\nCoffee,5.00\n")

    result = process_document(document_id, csv_path, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "completed"
    assert result.document_id == document_id
    assert result.chunk_count == 1
    assert result.embedding_dimensions == 1536
    assert len(fake_supabase.tables["document_chunks"]) == 1


def test_process_document_marks_failed_and_reraises_on_parse_error(
    fake_supabase, fake_settings, mocker, tmp_path
):
    document_id = create_pending_document("broken.pdf", settings=fake_settings)
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"not a real pdf")

    mocker.patch("rag_pipeline.ingest.parse_document", side_effect=ValueError("boom"))

    with pytest.raises(ValueError, match="boom"):
        process_document(document_id, pdf_path, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "failed"


def test_process_document_marks_failed_and_reraises_on_embedding_error(
    fake_supabase, fake_settings, mocker, tmp_path
):
    document_id = create_pending_document("statement.csv", settings=fake_settings)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text("description,amount\nCoffee,5.00\n")

    mocker.patch(
        "rag_pipeline.ingest.embed_texts", side_effect=RuntimeError("openai down")
    )

    with pytest.raises(RuntimeError, match="openai down"):
        process_document(document_id, csv_path, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "failed"


def test_process_document_raises_for_missing_file(fake_supabase, fake_settings):
    document_id = create_pending_document("gone.pdf", settings=fake_settings)

    with pytest.raises(FileNotFoundError):
        process_document(document_id, "/nonexistent/path/gone.pdf", settings=fake_settings)


def test_mark_document_failed_sets_status(fake_supabase, fake_settings):
    document_id = create_pending_document("statement.csv", settings=fake_settings)

    mark_document_failed(document_id, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "failed"


def test_ingest_document_wraps_create_and_process(
    fake_supabase, fake_settings, fake_embeddings, tmp_path
):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("description,amount\nCoffee,5.00\n")

    result = ingest_document(csv_path, settings=fake_settings)

    assert result.filename == "data.csv"
    row = next(
        r for r in fake_supabase.tables["documents"] if r["id"] == result.document_id
    )
    assert row["status"] == "completed"

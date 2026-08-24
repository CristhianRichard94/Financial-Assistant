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

USER_ID = "11111111-1111-1111-1111-111111111111"


def test_create_pending_document_inserts_row_with_metadata(fake_supabase, fake_settings):
    document_id = create_pending_document(
        "statement.pdf", USER_ID, metadata={"size_bytes": 1234}, settings=fake_settings
    )

    rows = fake_supabase.tables["documents"]
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == document_id
    assert row["filename"] == "statement.pdf"
    assert row["user_id"] == USER_ID
    assert row["metadata"] == {"size_bytes": 1234, "document_type": "pdf"}
    # Status is left for the table's own default ("pending") to apply.
    assert row["status"] == "pending"


def test_create_pending_document_defaults_metadata_to_inferred_document_type(
    fake_supabase, fake_settings
):
    create_pending_document("no_metadata.csv", USER_ID, settings=fake_settings)

    row = fake_supabase.tables["documents"][0]
    assert row["metadata"] == {"document_type": "csv"}


def test_create_pending_document_infers_document_type_for_pdf(
    fake_supabase, fake_settings
):
    create_pending_document("statement.pdf", USER_ID, settings=fake_settings)

    row = fake_supabase.tables["documents"][0]
    assert row["metadata"]["document_type"] == "pdf"


def test_create_pending_document_infers_document_type_for_image(
    fake_supabase, fake_settings
):
    create_pending_document("receipt.jpg", USER_ID, settings=fake_settings)

    row = fake_supabase.tables["documents"][0]
    assert row["metadata"]["document_type"] == "image"


def test_create_pending_document_does_not_clobber_existing_document_type(
    fake_supabase, fake_settings
):
    create_pending_document(
        "statement.pdf",
        USER_ID,
        metadata={"document_type": "custom"},
        settings=fake_settings,
    )

    row = fake_supabase.tables["documents"][0]
    assert row["metadata"]["document_type"] == "custom"


def test_create_pending_document_leaves_unrecognized_extension_without_document_type(
    fake_supabase, fake_settings
):
    create_pending_document("notes.txt", USER_ID, settings=fake_settings)

    row = fake_supabase.tables["documents"][0]
    assert "document_type" not in row["metadata"]


def test_process_document_marks_completed_on_success(
    fake_supabase, fake_settings, fake_embeddings, tmp_path
):
    document_id = create_pending_document("statement.csv", USER_ID, settings=fake_settings)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text("description,amount\nCoffee,5.00\n")

    result = process_document(document_id, csv_path, USER_ID, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "completed"
    assert result.document_id == document_id
    assert result.chunk_count == 1
    assert result.embedding_dimensions == 1536
    chunk_rows = fake_supabase.tables["document_chunks"]
    assert len(chunk_rows) == 1
    assert chunk_rows[0]["user_id"] == USER_ID


def test_process_document_marks_failed_and_reraises_on_parse_error(
    fake_supabase, fake_settings, mocker, tmp_path
):
    document_id = create_pending_document("broken.pdf", USER_ID, settings=fake_settings)
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"not a real pdf")

    mocker.patch("rag_pipeline.ingest.parse_document", side_effect=ValueError("boom"))

    with pytest.raises(ValueError, match="boom"):
        process_document(document_id, pdf_path, USER_ID, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "failed"
    assert row["metadata"]["error"] == "boom"
    # Pre-existing metadata (set at create_pending_document time) must survive
    # the failure update, not get clobbered.
    assert row["metadata"]["document_type"] == "pdf"


def test_process_document_marks_failed_with_friendly_message_on_no_extractable_text(
    fake_supabase, fake_settings, mocker, tmp_path
):
    document_id = create_pending_document("landscape.jpg", USER_ID, settings=fake_settings)
    image_path = tmp_path / "landscape.jpg"
    image_path.write_bytes(b"not a real jpg")

    mocker.patch("rag_pipeline.ingest.parse_document", return_value="")

    with pytest.raises(ValueError, match="No text could be read"):
        process_document(document_id, image_path, USER_ID, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "failed"
    assert "No text could be read" in row["metadata"]["error"]


def test_process_document_marks_failed_and_reraises_on_embedding_error(
    fake_supabase, fake_settings, mocker, tmp_path
):
    document_id = create_pending_document("statement.csv", USER_ID, settings=fake_settings)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text("description,amount\nCoffee,5.00\n")

    mocker.patch(
        "rag_pipeline.ingest.embed_texts", side_effect=RuntimeError("openai down")
    )

    with pytest.raises(RuntimeError, match="openai down"):
        process_document(document_id, csv_path, USER_ID, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "failed"


def test_process_document_raises_for_missing_file(fake_supabase, fake_settings):
    document_id = create_pending_document("gone.pdf", USER_ID, settings=fake_settings)

    with pytest.raises(FileNotFoundError):
        process_document(
            document_id, "/nonexistent/path/gone.pdf", USER_ID, settings=fake_settings
        )


def test_mark_document_failed_sets_status(fake_supabase, fake_settings):
    document_id = create_pending_document("statement.csv", USER_ID, settings=fake_settings)

    mark_document_failed(document_id, settings=fake_settings)

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "failed"
    assert row["metadata"]["error"] == "Failed to process this document."


def test_process_document_inserts_transactions_for_csv_with_transaction_rows(
    fake_supabase, fake_settings, fake_embeddings, tmp_path
):
    document_id = create_pending_document("statement.csv", USER_ID, settings=fake_settings)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text(
        "Date,Description,Category,Amount\n"
        "2026-01-15,Coffee Shop,Dining,-4.50\n"
        "2026-01-16,Paycheck,Income,2000.00\n"
    )

    process_document(document_id, csv_path, USER_ID, settings=fake_settings)

    transaction_rows = fake_supabase.tables["transactions"]
    assert len(transaction_rows) == 2
    assert all(row["document_id"] == document_id for row in transaction_rows)
    assert all(row["user_id"] == USER_ID for row in transaction_rows)
    assert transaction_rows[0]["amount"] == "-4.5"
    assert transaction_rows[0]["category"] == "Dining"
    assert transaction_rows[0]["occurred_on"] == "2026-01-15"

    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "completed"


def test_process_document_pdf_never_touches_transactions_table(
    fake_supabase, fake_settings, fake_embeddings, tmp_path, mocker
):
    document_id = create_pending_document("statement.pdf", USER_ID, settings=fake_settings)
    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    mocker.patch("rag_pipeline.ingest.parse_document", return_value="Some extracted text")

    process_document(document_id, pdf_path, USER_ID, settings=fake_settings)

    assert "transactions" not in fake_supabase.tables
    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "completed"


def test_process_document_csv_with_zero_parseable_transactions_still_completes(
    fake_supabase, fake_settings, fake_embeddings, tmp_path
):
    document_id = create_pending_document("not_transactions.csv", USER_ID, settings=fake_settings)
    csv_path = tmp_path / "not_transactions.csv"
    csv_path.write_text("First Name,Last Name,Email\nJane,Doe,jane@example.com\n")

    process_document(document_id, csv_path, USER_ID, settings=fake_settings)

    assert fake_supabase.tables.get("transactions", []) == []
    row = next(r for r in fake_supabase.tables["documents"] if r["id"] == document_id)
    assert row["status"] == "completed"


def test_ingest_document_wraps_create_and_process(
    fake_supabase, fake_settings, fake_embeddings, tmp_path
):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("description,amount\nCoffee,5.00\n")

    result = ingest_document(csv_path, USER_ID, settings=fake_settings)

    assert result.filename == "data.csv"
    row = next(
        r for r in fake_supabase.tables["documents"] if r["id"] == result.document_id
    )
    assert row["status"] == "completed"
    assert row["user_id"] == USER_ID

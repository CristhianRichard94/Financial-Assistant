"""Tests for rag_pipeline.documents: list_documents, get_document, delete_document."""

from __future__ import annotations

from rag_pipeline.documents import DocumentRecord, delete_document, get_document, list_documents
from rag_pipeline.ingest import create_pending_document

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


def test_list_documents_orders_by_upload_date_desc(fake_supabase, fake_settings):
    first_id = create_pending_document("first.pdf", USER_ID, settings=fake_settings)
    fake_supabase.tables["documents"][0]["upload_date"] = "2026-01-01T00:00:00+00:00"
    second_id = create_pending_document("second.pdf", USER_ID, settings=fake_settings)
    fake_supabase.tables["documents"][1]["upload_date"] = "2026-02-01T00:00:00+00:00"

    records = list_documents(USER_ID, settings=fake_settings)

    assert [record.id for record in records] == [second_id, first_id]
    assert all(isinstance(record, DocumentRecord) for record in records)


def test_list_documents_excludes_other_users_documents(fake_supabase, fake_settings):
    create_pending_document("mine.pdf", USER_ID, settings=fake_settings)
    create_pending_document("theirs.pdf", OTHER_USER_ID, settings=fake_settings)

    records = list_documents(USER_ID, settings=fake_settings)

    assert [record.filename for record in records] == ["mine.pdf"]


def test_get_document_returns_record_when_found(fake_supabase, fake_settings):
    document_id = create_pending_document(
        "doc.csv", USER_ID, metadata={"size_bytes": 42}, settings=fake_settings
    )

    record = get_document(document_id, USER_ID, settings=fake_settings)

    assert record is not None
    assert record.id == document_id
    assert record.filename == "doc.csv"
    assert record.status == "pending"
    assert record.metadata == {"size_bytes": 42}


def test_get_document_returns_none_when_missing(fake_supabase, fake_settings):
    assert get_document("does-not-exist", USER_ID, settings=fake_settings) is None


def test_get_document_returns_none_when_owned_by_another_user(fake_supabase, fake_settings):
    document_id = create_pending_document("theirs.pdf", OTHER_USER_ID, settings=fake_settings)

    assert get_document(document_id, USER_ID, settings=fake_settings) is None


def test_delete_document_returns_true_when_deleted(fake_supabase, fake_settings):
    document_id = create_pending_document("doc.pdf", USER_ID, settings=fake_settings)

    assert delete_document(document_id, USER_ID, settings=fake_settings) is True
    assert get_document(document_id, USER_ID, settings=fake_settings) is None


def test_delete_document_returns_false_when_not_found(fake_supabase, fake_settings):
    assert delete_document("does-not-exist", USER_ID, settings=fake_settings) is False


def test_delete_document_returns_false_when_owned_by_another_user(fake_supabase, fake_settings):
    document_id = create_pending_document("theirs.pdf", OTHER_USER_ID, settings=fake_settings)

    assert delete_document(document_id, USER_ID, settings=fake_settings) is False
    # The row must still exist afterwards - it was never actually deleted.
    assert get_document(document_id, OTHER_USER_ID, settings=fake_settings) is not None

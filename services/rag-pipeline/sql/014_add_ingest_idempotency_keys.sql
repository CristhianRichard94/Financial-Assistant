-- Adds an idempotency key to each table rag_pipeline/ingest.py writes to,
-- so a retried insert after an ambiguous timeout (see rag_pipeline/retry.py)
-- upserts onto the same row instead of creating a duplicate (see issue #38
-- and rag_pipeline/ingest.py's `_idempotency_key` helper for how the key
-- itself is computed).
--
-- Nullable + a partial unique index (rather than `not null unique`) so
-- existing rows inserted before this migration - which have no
-- idempotency_key - are never treated as conflicting with each other or
-- with a new row.
alter table documents add column if not exists idempotency_key text;
create unique index if not exists documents_idempotency_key_idx
    on documents (idempotency_key)
    where idempotency_key is not null;

alter table document_chunks add column if not exists idempotency_key text;
create unique index if not exists document_chunks_idempotency_key_idx
    on document_chunks (idempotency_key)
    where idempotency_key is not null;

alter table transactions add column if not exists idempotency_key text;
create unique index if not exists transactions_idempotency_key_idx
    on transactions (idempotency_key)
    where idempotency_key is not null;

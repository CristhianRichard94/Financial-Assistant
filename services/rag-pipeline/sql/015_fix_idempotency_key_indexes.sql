-- Replaces the partial unique indexes created in 014 with plain unique
-- indexes on idempotency_key.
--
-- Why: rag_pipeline/ingest.py upserts with on_conflict="idempotency_key",
-- which PostgREST turns into a bare `ON CONFLICT (idempotency_key)`.
-- Postgres cannot infer a partial index (`where idempotency_key is not null`)
-- for that clause, so every upsert failed with 42P10 "there is no unique or
-- exclusion constraint matching the ON CONFLICT specification".
--
-- Legacy rows with a NULL idempotency_key are still fine: NULLs are distinct
-- in a Postgres unique index, so they never conflict with each other.
begin;

drop index if exists documents_idempotency_key_idx;
create unique index if not exists documents_idempotency_key_idx
    on documents (idempotency_key);

drop index if exists document_chunks_idempotency_key_idx;
create unique index if not exists document_chunks_idempotency_key_idx
    on document_chunks (idempotency_key);

drop index if exists transactions_idempotency_key_idx;
create unique index if not exists transactions_idempotency_key_idx
    on transactions (idempotency_key);

commit;

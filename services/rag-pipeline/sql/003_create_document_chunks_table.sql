-- One row per chunk of a document, along with its embedding.
-- Requires 001_enable_pgvector.sql and 002_create_documents_table.sql to have
-- been run first.
create table if not exists document_chunks (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents (id) on delete cascade,
    chunk_text text not null,
    chunk_index int not null,
    embedding vector(1536),
    metadata jsonb not null default '{}'::jsonb
);

comment on table document_chunks is 'Chunks of ingested documents with their embeddings, used for similarity search.';
comment on column document_chunks.embedding is 'text-embedding-3-small embedding (1536 dimensions).';

create index if not exists document_chunks_document_id_idx
    on document_chunks (document_id);

-- One row per ingested source document (PDF, CSV, etc.).
create table if not exists documents (
    id uuid primary key default gen_random_uuid(),
    filename text not null,
    upload_date timestamptz not null default now(),
    status text not null default 'pending',
    metadata jsonb not null default '{}'::jsonb
);

comment on table documents is 'Source documents ingested into the RAG pipeline.';
comment on column documents.status is 'Ingestion status, e.g. pending, processing, completed, failed.';

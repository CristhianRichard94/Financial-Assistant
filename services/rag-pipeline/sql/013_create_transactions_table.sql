-- Structured transaction rows extracted from ingested CSV bank exports (see
-- rag_pipeline/transactions.py and the CSV-only branch of
-- rag_pipeline/ingest.py's process_document()). PDFs/images never populate
-- this table - only embedded text chunks (document_chunks) exist for those.
--
-- `amount` is signed: positive = income, negative = spending. This lets the
-- dashboard aggregate income/spending/net savings and per-category spending
-- breakdowns with simple sign-based filtering rather than a separate
-- transaction "type" column.
--
-- Mirrors 007_add_user_scoping.sql's style: `user_id` denormalized directly
-- onto this table (not just inferred via a join to `documents`) so RLS
-- policies and dashboard aggregation queries can filter on
-- transactions.user_id directly.
create table transactions (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    occurred_on date not null,
    amount numeric(12, 2) not null,
    category text not null default 'Uncategorized',
    description text not null default '',
    created_at timestamptz not null default now()
);

create index transactions_user_id_occurred_on_idx
    on transactions (user_id, occurred_on desc);

create index transactions_document_id_idx
    on transactions (document_id);

alter table transactions enable row level security;

-- RLS policies for the `authenticated` role. As with `documents`/
-- `document_chunks` (see 006_enable_row_level_security.sql and
-- 007_add_user_scoping.sql), the app itself always accesses this table via
-- the service-role key (which bypasses RLS entirely), so these policies are
-- defense in depth for any future caller that authenticates as a regular
-- Supabase Auth user rather than the service role: it must never see or
-- modify another user's transactions. No update policy is defined -
-- transactions are only ever inserted at ingest time or deleted (via
-- cascade from their parent document), never edited in place.
create policy "Users can select their own transactions"
    on transactions for select
    to authenticated
    using (user_id = auth.uid());

create policy "Users can insert their own transactions"
    on transactions for insert
    to authenticated
    with check (user_id = auth.uid());

create policy "Users can delete their own transactions"
    on transactions for delete
    to authenticated
    using (user_id = auth.uid());

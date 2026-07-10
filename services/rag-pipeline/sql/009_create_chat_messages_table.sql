-- Chat history for the FinSight Next.js app (artifacts/finsight). This is
-- the only table in this migration folder that rag-pipeline/rag-api never
-- touch - Next.js is the sole reader/writer, via the user's own
-- session (anon key + cookies), never a service-role key. It lives here
-- anyway because this folder is the repo's single source of truth for the
-- Supabase schema.
create table if not exists chat_messages (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz not null default now()
);

comment on table chat_messages is 'Per-user chat history for the FinSight assistant, read/written directly by the Next.js app.';

create index if not exists chat_messages_user_id_created_at_idx
    on chat_messages (user_id, created_at);

-- RLS is the *actual* access control for this table (unlike
-- documents/document_chunks, which the app only ever accesses via a
-- service-role key - see 006_enable_row_level_security.sql): Next.js reads
-- and writes chat_messages using the caller's own session, so these
-- policies are what keeps one user from ever seeing or inserting into
-- another user's chat history.
alter table chat_messages enable row level security;

create policy "Users can select their own chat messages"
    on chat_messages for select
    to authenticated
    using (user_id = auth.uid());

create policy "Users can insert their own chat messages"
    on chat_messages for insert
    to authenticated
    with check (user_id = auth.uid());

-- No update/delete policies: chat is append-only, matching the previous
-- in-memory store's behavior (src/lib/store.ts's `store.chat.add` never
-- mutated or removed existing messages).

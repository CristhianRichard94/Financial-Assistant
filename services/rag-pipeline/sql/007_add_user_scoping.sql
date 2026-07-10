-- Multi-tenancy: scope `documents` and `document_chunks` rows to the
-- Supabase Auth user that owns them, and add RLS policies enforcing that
-- scoping for any caller using the `authenticated` role.
--
-- This app is pre-launch (no real users/production data in any environment
-- at the time this migration was written), so a plain `not null` column
-- with no default and no backfill step is fine here: if this is ever run
-- against a database that already has rows in `documents`/`document_chunks`,
-- it will fail loudly with a not-null violation instead of silently
-- assigning an arbitrary owner - that's the desired behavior.
alter table documents
    add column user_id uuid not null references auth.users (id) on delete cascade;

create index if not exists documents_user_id_idx
    on documents (user_id);

-- Denormalized onto document_chunks too (not just inferred via a join to
-- documents) so RLS policies and the match_document_chunks search RPC (see
-- 008_scope_match_document_chunks_by_user.sql) can filter on
-- document_chunks.user_id directly, without joining to documents on every
-- chunk read.
alter table document_chunks
    add column user_id uuid not null references auth.users (id) on delete cascade;

create index if not exists document_chunks_user_id_idx
    on document_chunks (user_id);

-- RLS policies for the `authenticated` role. The app itself always accesses
-- these tables via the service-role key (which bypasses RLS entirely - see
-- 006_enable_row_level_security.sql), so these policies are defense in
-- depth for any future caller that authenticates as a regular Supabase Auth
-- user rather than the service role: it must never see or modify another
-- user's rows.
create policy "Users can select their own documents"
    on documents for select
    to authenticated
    using (user_id = auth.uid());

create policy "Users can insert their own documents"
    on documents for insert
    to authenticated
    with check (user_id = auth.uid());

create policy "Users can update their own documents"
    on documents for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "Users can delete their own documents"
    on documents for delete
    to authenticated
    using (user_id = auth.uid());

create policy "Users can select their own document chunks"
    on document_chunks for select
    to authenticated
    using (user_id = auth.uid());

create policy "Users can insert their own document chunks"
    on document_chunks for insert
    to authenticated
    with check (user_id = auth.uid());

create policy "Users can update their own document chunks"
    on document_chunks for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "Users can delete their own document chunks"
    on document_chunks for delete
    to authenticated
    using (user_id = auth.uid());

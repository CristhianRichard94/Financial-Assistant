-- Enable Row Level Security on tables exposed via Supabase's public REST API.
--
-- The rag-pipeline app only ever accesses these tables through the
-- service-role key, which bypasses RLS entirely. No policies are defined
-- here on purpose: with RLS enabled and zero policies, the anon and
-- authenticated roles are denied all access by default, while service_role
-- continues to have full read/write access as before. This closes off
-- accidental public read/write access to documents and document_chunks via
-- the anon key without changing how the application itself behaves.
alter table documents enable row level security;
alter table document_chunks enable row level security;

-- Enable the pgvector extension so we can store and index embedding vectors.
-- Supabase ships pgvector as an available extension; this just turns it on
-- for the current database.
create extension if not exists vector;

-- Add a full-text search signal on document_chunks.chunk_text.
--
-- Pure pgvector cosine similarity (see sql/004_create_embedding_hnsw_index.sql)
-- can miss exact keyword/number matches that matter a lot for financial
-- documents, e.g. an account number, a specific merchant name, or a check
-- number, where semantic similarity is close but not the top match. A
-- Postgres full-text-search column gives us a second, keyword-based ranked
-- list to fuse with the vector-similarity ranked list (see
-- sql/011_create_match_document_chunks_hybrid_function.sql).
--
-- The tsvector column is a generated/stored column so it is computed once at
-- write time (not recomputed on every query) and can be indexed directly.
alter table document_chunks
    add column if not exists chunk_text_tsv tsvector
    generated always as (to_tsvector('english', chunk_text)) stored;

create index if not exists document_chunks_chunk_text_tsv_idx
    on document_chunks using gin (chunk_text_tsv);

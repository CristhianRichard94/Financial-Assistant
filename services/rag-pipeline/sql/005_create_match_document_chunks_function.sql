-- RPC used by the Python client for similarity search. Supabase automatically
-- exposes any SQL function on the `public` schema as a callable RPC endpoint
-- (supabase.rpc("match_document_chunks", {...}) from supabase-py).
--
-- Cosine similarity is derived from pgvector's `<=>` cosine-distance operator
-- as `1 - distance`, so results are ordered most-similar first (similarity
-- close to 1 = near-identical, close to 0 = unrelated, negative = opposite).
create or replace function match_document_chunks (
    query_embedding vector(1536),
    match_count int default 5
)
returns table (
    id uuid,
    document_id uuid,
    chunk_text text,
    chunk_index int,
    metadata jsonb,
    filename text,
    similarity float
)
language sql
stable
as $$
    select
        document_chunks.id,
        document_chunks.document_id,
        document_chunks.chunk_text,
        document_chunks.chunk_index,
        document_chunks.metadata,
        documents.filename,
        1 - (document_chunks.embedding <=> query_embedding) as similarity
    from document_chunks
    join documents on documents.id = document_chunks.document_id
    order by document_chunks.embedding <=> query_embedding
    limit match_count;
$$;

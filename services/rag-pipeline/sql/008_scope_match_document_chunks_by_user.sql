-- Scope match_document_chunks similarity search to a single user's chunks.
--
-- Adds a required `p_user_id uuid` parameter with no default, so a caller
-- that forgets to pass it gets a hard Postgres error ("function
-- match_document_chunks(vector, integer) does not exist") instead of
-- silently searching every user's data.
--
-- Postgres requires that once a parameter has a default value, every
-- parameter after it in the declaration must have a default too (see
-- https://www.postgresql.org/docs/current/sql-createfunction.html). Since
-- p_user_id must stay required (no default) and is the newly-added third
-- parameter, match_count's previous `default 5` is dropped here as well -
-- rag_pipeline.search() (the only caller) always passes match_count
-- explicitly, so this has no functional effect on the application.
--
-- Changing the parameter list is an incompatible signature change, so the
-- old two-argument version must be dropped first; `create or replace`
-- cannot alter a function's parameter types/count in place.
drop function if exists match_document_chunks(vector(1536), int);

create function match_document_chunks (
    query_embedding vector(1536),
    match_count int,
    p_user_id uuid
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
    where document_chunks.user_id = p_user_id
    order by document_chunks.embedding <=> query_embedding
    limit match_count;
$$;

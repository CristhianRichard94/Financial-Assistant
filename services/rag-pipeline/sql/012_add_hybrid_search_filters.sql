-- Add optional date-range/document-type filters to the hybrid search RPC,
-- fed by the new query-parsing layer (see
-- services/rag-api/rag_api/query_parser.py) which extracts structured
-- filters from the user's raw question before retrieval.
--
-- `create or replace function` with the same function name
-- (match_document_chunks_hybrid) keeps this additive over
-- sql/011_create_match_document_chunks_hybrid_function.sql: 011 is left
-- untouched, this migration only replaces the function body/signature.
-- The pre-existing params (query_embedding, query_text, match_count,
-- p_user_id, p_candidate_pool) keep their exact names/order/defaults; the
-- new filter params are appended after them, all defaulting to null so
-- existing named-param RPC calls (`supabase.rpc(name, {...})`) that don't
-- pass them keep working unfiltered.
--
-- Filters are applied against the joined `documents` row:
--   * p_date_from / p_date_to: inclusive bounds on documents.upload_date.
--   * p_document_type: exact match against documents.metadata->>'document_type'
--     (populated at ingestion time - see rag_pipeline.ingest.create_pending_document).
-- Each filter is a no-op (matches everything) when left null.
create or replace function match_document_chunks_hybrid (
    query_embedding vector(1536),
    query_text text,
    match_count int,
    p_user_id uuid,
    p_candidate_pool int default greatest(match_count * 4, 20),
    p_date_from timestamptz default null,
    p_date_to timestamptz default null,
    p_document_type text default null
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
    with vector_ranked as (
        select
            document_chunks.id,
            row_number() over (
                order by document_chunks.embedding <=> query_embedding
            ) as rank
        from document_chunks
        join documents on documents.id = document_chunks.document_id
        where document_chunks.user_id = p_user_id
            and (p_date_from is null or documents.upload_date::date >= p_date_from::date)
            and (p_date_to is null or documents.upload_date::date <= p_date_to::date)
            and (p_document_type is null or documents.metadata->>'document_type' = p_document_type)
        order by document_chunks.embedding <=> query_embedding
        limit p_candidate_pool
    ),
    fts_ranked as (
        select
            document_chunks.id,
            row_number() over (
                order by ts_rank(
                    document_chunks.chunk_text_tsv,
                    plainto_tsquery('english', query_text)
                ) desc
            ) as rank
        from document_chunks
        join documents on documents.id = document_chunks.document_id
        where document_chunks.user_id = p_user_id
            and document_chunks.chunk_text_tsv @@ plainto_tsquery('english', query_text)
            and (p_date_from is null or documents.upload_date::date >= p_date_from::date)
            and (p_date_to is null or documents.upload_date::date <= p_date_to::date)
            and (p_document_type is null or documents.metadata->>'document_type' = p_document_type)
        order by ts_rank(
            document_chunks.chunk_text_tsv,
            plainto_tsquery('english', query_text)
        ) desc
        limit p_candidate_pool
    ),
    fused as (
        select
            coalesce(vector_ranked.id, fts_ranked.id) as id,
            coalesce(1.0 / (60 + vector_ranked.rank), 0)
                + coalesce(1.0 / (60 + fts_ranked.rank), 0) as fused_score
        from vector_ranked
        full outer join fts_ranked on fts_ranked.id = vector_ranked.id
    )
    select
        document_chunks.id,
        document_chunks.document_id,
        document_chunks.chunk_text,
        document_chunks.chunk_index,
        document_chunks.metadata,
        documents.filename,
        fused.fused_score as similarity
    from fused
    join document_chunks on document_chunks.id = fused.id
    join documents on documents.id = document_chunks.document_id
    order by fused.fused_score desc
    limit match_count;
$$;

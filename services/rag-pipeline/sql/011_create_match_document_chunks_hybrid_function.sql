-- Hybrid (vector + full-text) chunk search with reciprocal rank fusion (RRF).
--
-- This is additive: the existing match_document_chunks function (see
-- sql/008_scope_match_document_chunks_by_user.sql) is left in place, unused,
-- as a fallback/reference. rag_pipeline.search() (see
-- services/rag-pipeline/rag_pipeline/search.py) now calls this function
-- instead.
--
-- Two candidate lists are built, each scoped to p_user_id and capped at
-- p_candidate_pool rows, and each ranked independently:
--   * vector_ranked: cosine distance over the HNSW index (see
--     sql/004_create_embedding_hnsw_index.sql).
--   * fts_ranked: Postgres full-text search rank over chunk_text_tsv (see
--     sql/010_add_chunk_text_fts_index.sql). A query_text with no lexemes
--     that match anything (or that plainto_tsquery reduces to an empty
--     tsquery) simply contributes zero rows here rather than erroring -
--     plainto_tsquery('english', '') is a valid, always-empty tsquery, and
--     `to_tsvector @@ empty_tsquery` matches nothing rather than raising.
--
-- The two ranked lists are then full-outer-joined on chunk id and combined
-- with a standard RRF formula (1 / (60 + rank), k=60 is the usual RRF
-- constant), summing across whichever list(s) a given chunk appears in.
--
-- The result column is still named `similarity` for API compatibility with
-- the existing rag_pipeline.search.SearchResult.similarity field - but it is
-- no longer a raw cosine similarity, it is the fused RRF score.
create function match_document_chunks_hybrid (
    query_embedding vector(1536),
    query_text text,
    match_count int,
    p_user_id uuid,
    p_candidate_pool int default greatest(match_count * 4, 20)
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
        where document_chunks.user_id = p_user_id
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
        where document_chunks.user_id = p_user_id
            and document_chunks.chunk_text_tsv @@ plainto_tsquery('english', query_text)
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

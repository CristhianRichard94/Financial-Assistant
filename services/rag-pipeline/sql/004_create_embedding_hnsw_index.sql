-- HNSW index on the embedding column for fast approximate cosine-similarity
-- search. HNSW is pgvector's current recommended default (better query-time
-- recall/latency trade-off than ivfflat, and it does not need to be built
-- against a pre-populated table the way ivfflat does).
--
-- vector_cosine_ops matches the `<=>` cosine-distance operator used in
-- 005_create_match_document_chunks_function.sql.
create index if not exists document_chunks_embedding_hnsw_idx
    on document_chunks
    using hnsw (embedding vector_cosine_ops);

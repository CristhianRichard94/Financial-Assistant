# RAG Document Pipeline

A standalone Python service that ingests documents (PDF, CSV) into a
Supabase/pgvector-backed store and answers similarity-search queries over
them. It's the retrieval-augmented-generation (RAG) backend for FinSight,
built independently from the rest of the (TypeScript) monorepo — it has its
own Supabase project, its own Python dependencies, and no shared code with
`lib/db` or the Next.js/Express apps.

This is a library with a runnable test script, not a web service: there's no
HTTP server or UI here.

## How it works

1. **Parse** — `rag_pipeline/parsing.py` extracts raw text from a local PDF
   (via `pypdf`) or CSV file.
2. **Chunk** — `rag_pipeline/chunking.py` splits that text into ~500-token
   chunks with ~50-token overlap, counted with `tiktoken`'s `cl100k_base`
   encoding (the encoding used by `text-embedding-3-small`).
3. **Embed** — `rag_pipeline/embeddings.py` calls OpenAI's
   `text-embedding-3-small` to turn each chunk into a 1536-dimension vector.
4. **Store** — `rag_pipeline/ingest.py` inserts one row into `documents` and
   one row per chunk into `document_chunks` via `supabase-py`.
5. **Search** — `rag_pipeline/search.py` embeds a query string the same way
   and calls the `match_document_chunks` Postgres function (exposed by
   Supabase as an RPC) to get the top-k most similar chunks by cosine
   similarity, using an HNSW index for fast lookup.

## Setup

### 1. Create a new Supabase project

Create a new project at https://supabase.com/dashboard (this is intentionally
a separate project from anything else FinSight uses — this pipeline owns its
own database).

### 2. Run the SQL migrations

Open the Supabase dashboard's **SQL Editor** and run the files under
[`sql/`](./sql) **in numeric order**:

1. `001_enable_pgvector.sql` — enables the `vector` extension.
2. `002_create_documents_table.sql` — creates the `documents` table.
3. `003_create_document_chunks_table.sql` — creates the `document_chunks`
   table (references `documents`, stores a `vector(1536)` embedding column).
4. `004_create_embedding_hnsw_index.sql` — adds an HNSW index
   (`vector_cosine_ops`) on `document_chunks.embedding` for fast
   cosine-similarity search.
5. `005_create_match_document_chunks_function.sql` — creates the
   `match_document_chunks(query_embedding, match_count)` SQL function, which
   Supabase automatically exposes as an RPC callable from `supabase-py`.
6. `006_enable_row_level_security.sql` — enables Row Level Security on
   `documents` and `document_chunks`.

**Do not skip step 6.** Without it, both tables are readable and writable by
anyone holding the project's `anon` key over Supabase's auto-generated REST
API, regardless of any policies you add later — RLS must be enabled for
table-level access control to apply at all.

Each file is idempotent (`create ... if not exists` / `create or replace`),
so re-running one is harmless if you need to reapply it.

### 3. Set environment variables

```bash
cp .env.example .env
# then edit .env with real values
```

| Variable | Where to find it |
| --- | --- |
| `SUPABASE_URL` | Supabase dashboard -> Project Settings -> API |
| `SUPABASE_SERVICE_KEY` | Supabase dashboard -> Project Settings -> API -> `service_role` secret key |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |

The service-role key is required (not the anon key) because ingestion writes
as a trusted backend job and needs to bypass row-level security.

### 4. Install dependencies

```bash
cd services/rag-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Running the test script

```bash
python scripts/test_ingest_and_query.py
```

This ingests the sample files in [`sample_data/`](./sample_data)
(`sample_budget_guide.pdf`, a short personal-finance guide, and
`sample_transactions.csv`, a small set of finance transactions), then runs a
test query and prints:

- total number of chunks inserted across both files,
- the embedding dimensionality (should be 1536),
- the top-k retrieved chunks with their cosine similarity scores, chunk
  metadata, and source filename, so you can sanity-check relevance by eye.

If `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, or `OPENAI_API_KEY` aren't set, the
script prints a clear message and exits instead of crashing with a raw
traceback.

The sample PDF was generated with `scripts/generate_sample_pdf.py` (needs the
optional `dev` extra: `pip install -e ".[dev]"`); you only need to rerun that
if you want to regenerate or edit it.

## Using it as a library

```python
from rag_pipeline import ingest_document, search

result = ingest_document("statement.pdf")
print(result.chunk_count, result.embedding_dimensions)

for hit in search("What did I spend on groceries last month?", k=5):
    print(hit.similarity, hit.filename, hit.chunk_text)
```

Both `ingest_document` and `search` read `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY`, and `OPENAI_API_KEY` from the environment by default
(via `python-dotenv`, loading `.env` if present), or accept an explicit
`Settings` object (`rag_pipeline.config.load_settings()`).

## Project layout

```
services/rag-pipeline/
  sql/                     Numbered SQL migrations to run in Supabase
  rag_pipeline/            The Python package
    config.py              Env var loading + chunking/embedding constants
    parsing.py             PDF/CSV -> raw text
    chunking.py             Token-aware chunking (tiktoken)
    embeddings.py           OpenAI text-embedding-3-small calls
    supabase_client.py       supabase-py client factory
    ingest.py               Parse -> chunk -> embed -> insert pipeline
    search.py                Query embedding + match_document_chunks RPC
  scripts/
    test_ingest_and_query.py  End-to-end sanity check (needs real credentials)
    generate_sample_pdf.py    Regenerates the sample PDF (dev-only helper)
  sample_data/               Small sample PDF + CSV used by the test script
  pyproject.toml
  .env.example
```

## Known limitations / things to verify with real credentials

- The test script and ingestion pipeline haven't been run end-to-end against
  a live Supabase project or the real OpenAI API in this environment — only
  parsing and chunking were exercised locally. Double-check the Supabase RPC
  call shape and insert payloads against your actual project once you have
  credentials.
- Re-running the test script re-ingests the sample files as new `documents`
  rows each time (no dedup/upsert-by-filename logic), so repeated runs will
  accumulate duplicate documents in your Supabase project. Delete rows
  between runs, or extend `ingest_document` with an upsert-by-filename check,
  if that matters for your workflow.
- Large PDFs/CSVs are parsed and embedded fully in memory and in a single
  embeddings request per file; very large documents may need batching the
  OpenAI call (it has a per-request input size limit) or streaming the parse
  step.

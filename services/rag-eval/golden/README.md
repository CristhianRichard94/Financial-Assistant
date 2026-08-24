# Golden dataset

`dataset.yaml` holds the golden evaluation cases used by `evals/` and
`scripts/run_evals.py`. Each case is a question against the FinSight sample
corpus (`services/rag-pipeline/sample_data/`), plus a reference answer and
(optionally) expected retrieval context snippets.

## Prerequisite: ingest the sample corpus

This suite calls the real `rag_pipeline.search.search()` against Supabase -
it does not stub retrieval. Before running any eval, the sample corpus (or
an equivalent one that matches the questions/answers in `dataset.yaml`) must
already be ingested for the `EVAL_USER_ID` configured in `.env`.

From `services/rag-pipeline`:

```bash
pip install -e .
python - <<'PY'
from pathlib import Path
from rag_pipeline.config import load_settings
from rag_pipeline.ingest import ingest_document

settings = load_settings()
user_id = "00000000-0000-0000-0000-000000000001"  # match EVAL_USER_ID
sample_dir = Path("sample_data")
for path in (sample_dir / "sample_budget_guide.pdf", sample_dir / "sample_transactions.csv"):
    result = ingest_document(path, user_id, settings=settings)
    print(result.filename, result.chunk_count)
PY
```

(`scripts/test_ingest_and_query.py` in `rag-pipeline` does the same thing
plus a sanity-check query, and is a good reference if you'd rather run that
directly with `TEST_USER_ID` set to your `EVAL_USER_ID`.)

`user_id` must be a real row in `auth.users` (foreign key constraint on
`documents.user_id`) - create one via Supabase Auth if needed.

## Adding a new case

Add an entry to the `cases` list in `dataset.yaml`:

```yaml
- id: unique_snake_case_id
  input: "The question to ask."
  expected_output: "A reference answer DeepEval compares against."
  expected_retrieval_context:      # optional; falls back to expected_output
    - "A snippet a good retrieval should surface."
  document_type: pdf                # optional: pdf | csv | image
  date_from: "2026-06-01"           # optional, ISO 8601
  date_to: "2026-06-30"             # optional, ISO 8601
  tags: [budget_guide, retrieval, generation]
```

Tags are used by `evals/` to select subsets (e.g. `pytest evals -k transactions`)
and by `dataset.filter_by_tag()`. Keep `expected_output` and
`expected_retrieval_context` grounded in the actual sample corpus content so
scores stay meaningful - see `services/rag-pipeline/scripts/generate_sample_pdf.py`
for the budget guide's full text and `sample_transactions.csv` for the ledger.

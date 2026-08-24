# rag-eval

DeepEval-based RAG quality evaluation suite for FinSight. It exercises the
**real** production code paths - `rag_pipeline.search.search()` for
retrieval and `rag_api.openai_client.ask_openai()` for generation - against
a golden question/answer dataset, no mocks. This is intentionally separate
from the fast, fully-mocked `pytest` suites in `services/rag-api/tests` and
`services/rag-pipeline/tests`: it needs real OpenAI + Supabase calls (cost +
latency), and its tests live in `evals/`, not `tests/`, so it is never swept
up by a default `pytest`/CI run.

## What it evaluates

- **Retrieval quality** (`evals/test_retrieval_quality.py`): DeepEval's
  `ContextualPrecisionMetric`, `ContextualRecallMetric`, and
  `ContextualRelevancyMetric` - are the right chunks found, ranked well, and
  actually relevant to the question?
- **Generation quality** (`evals/test_generation_quality.py`): DeepEval's
  `FaithfulnessMetric` and `AnswerRelevancyMetric` - does the synthesized
  answer stick to the retrieved excerpts, and does it actually answer the
  question?
- **End-to-end** (`evals/test_end_to_end.py`): every golden case scored
  against all five metrics together. This is what `deepeval test run` is
  meant to be pointed at for a full report.

All metrics are judged by an OpenAI `GPTModel`, reusing this repo's existing
`OPENAI_API_KEY` (default judge model `gpt-5`, configurable via
`DEEPEVAL_JUDGE_MODEL`).

## Install

```bash
cd services/rag-eval
pip install -e ".[dev]"
```

This pulls in `rag-pipeline` and `rag-api` as local path dependencies (see
`pyproject.toml`) - the dependency is one-directional; neither of those
packages knows about `rag-eval`.

## Configure

```bash
cp .env.example .env
```

Fill in real `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`INTERNAL_API_KEY` (any placeholder value works - it's only required by
`rag_api.config.load_rag_api_settings()`, never used for HTTP auth here
since `ask_openai()` is called directly as a Python function), and
`EVAL_USER_ID`.

**Prerequisite**: the sample corpus (or an equivalent one matching
`golden/dataset.yaml`) must already be ingested for `EVAL_USER_ID` in
Supabase - see `golden/README.md`.

## Run

```bash
# DeepEval's own pytest wrapper - nicer report
deepeval test run evals/test_end_to_end.py

# plain pytest, targeted subset
pytest evals/ -k retrieval
pytest evals/ -k generation

# standalone, no pytest
python scripts/run_evals.py
python scripts/run_evals.py --tag transactions
```

Without `OPENAI_API_KEY`/`SUPABASE_URL`/`SUPABASE_SERVICE_KEY` set, the
`evals/` suite skips cleanly (via `evals/conftest.py`) instead of failing
opaquely - useful for confirming the package installs and imports correctly
without needing real credentials on hand.

## Adding golden cases

See `golden/README.md`.

## Non-goals

- No CI wiring here - this repo has no `.github` workflows, and this suite
  needs real API cost + a real seeded corpus, so it should stay a manual or
  nightly job if CI is added later, never part of default PR checks.
- `services/rag-api/tests` and `services/rag-pipeline/tests` (fully mocked)
  are untouched by this package.

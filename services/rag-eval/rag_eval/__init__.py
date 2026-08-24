"""DeepEval-based RAG quality evaluation suite for FinSight.

Exercises the real `rag_pipeline.search.search()` retrieval and
`rag_api.openai_client.ask_openai()` generation code paths (no mocks) against
a golden dataset, scoring retrieval and generation quality via DeepEval
metrics judged by an OpenAI model. See services/rag-eval/README.md.
"""

from __future__ import annotations

__all__: list[str] = []

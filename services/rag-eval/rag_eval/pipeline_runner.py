"""Runs the real, production RAG code path (no mocks) for evaluation.

This module is the only place in rag-eval that calls production code
directly: `rag_pipeline.search.search()` for retrieval and
`rag_api.openai_client.ask_openai()` for generation - the exact functions
`services/rag-api`'s HTTP routes call at request time. Evaluating anything
else (e.g. a reimplementation, or mocked versions) would tell us nothing
about actual production quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rag_api.config import load_rag_api_settings
from rag_api.openai_client import ask_openai
from rag_pipeline.config import load_settings as load_pipeline_settings
from rag_pipeline.search import SearchResult, search


@dataclass(frozen=True)
class PipelineOutput:
    """Everything a DeepEval `LLMTestCase` needs, plus the raw results for
    debugging/reporting.
    """

    question: str
    actual_output: str
    retrieval_context: list[str]
    results: list[SearchResult] = field(default_factory=list)


def run_pipeline(
    question: str,
    user_id: str,
    *,
    k: int = 5,
    date_from: str | None = None,
    date_to: str | None = None,
    document_type: str | None = None,
) -> PipelineOutput:
    """Run the real retrieval + generation pipeline for one golden question.

    Mirrors what `POST /query` does in services/rag-api: retrieve the top-k
    chunks for `question` scoped to `user_id`, then synthesize an answer from
    them via the real `gpt-5` chat model. No history is passed (single-turn),
    matching the plain /query route rather than the agentic /query/agent flow.
    """
    pipeline_settings = load_pipeline_settings()
    api_settings = load_rag_api_settings()

    results = search(
        question,
        user_id,
        k=k,
        settings=pipeline_settings,
        date_from=date_from,
        date_to=date_to,
        document_type=document_type,
    )

    answer, _sources = ask_openai(question, results, api_settings)

    return PipelineOutput(
        question=question,
        actual_output=answer or "",
        retrieval_context=[result.chunk_text for result in results],
        results=results,
    )

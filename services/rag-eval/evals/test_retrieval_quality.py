"""Retrieval-quality evals: contextual precision, recall, and relevancy.

Runs the real `rag_pipeline.search.search()` for each golden case (filtered
to cases tagged "retrieval") and scores the retrieved chunks against the
expected retrieval context with DeepEval's contextual metrics. Generation is
not exercised here - see test_generation_quality.py and test_end_to_end.py
for that.
"""

from __future__ import annotations

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from rag_pipeline.config import load_settings as load_pipeline_settings
from rag_pipeline.search import search

from rag_eval.dataset import filter_by_tag
from rag_eval.metrics import retrieval_metrics


def _retrieval_cases():
    from rag_eval.dataset import load_golden_cases

    return filter_by_tag(load_golden_cases(), "retrieval")


@pytest.mark.parametrize(
    "case", _retrieval_cases(), ids=lambda case: case.id
)
def test_retrieval_quality(case, eval_config):
    results = search(
        case.input,
        eval_config.eval_user_id,
        settings=load_pipeline_settings(),
        date_from=case.date_from,
        date_to=case.date_to,
        document_type=case.document_type,
    )

    test_case = LLMTestCase(
        input=case.input,
        actual_output=case.expected_output,  # not under test here; retrieval only
        expected_output=case.expected_output,
        retrieval_context=[result.chunk_text for result in results],
        expected_retrieval_context=case.expected_retrieval_context,
    )

    assert_test(test_case, retrieval_metrics(eval_config))

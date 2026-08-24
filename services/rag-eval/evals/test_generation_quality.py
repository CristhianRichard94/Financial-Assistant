"""Generation-quality evals: faithfulness and answer relevancy.

Runs the real end-to-end pipeline (`run_pipeline`, which calls both real
`search()` and real `ask_openai()`) for each golden case tagged "generation",
then scores the synthesized answer against the retrieved context and the
question with DeepEval's generation metrics.
"""

from __future__ import annotations

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from rag_eval.dataset import filter_by_tag, load_golden_cases
from rag_eval.metrics import generation_metrics
from rag_eval.pipeline_runner import run_pipeline


def _generation_cases():
    return filter_by_tag(load_golden_cases(), "generation")


@pytest.mark.parametrize(
    "case", _generation_cases(), ids=lambda case: case.id
)
def test_generation_quality(case, eval_config):
    output = run_pipeline(
        case.input,
        eval_config.eval_user_id,
        date_from=case.date_from,
        date_to=case.date_to,
        document_type=case.document_type,
    )

    test_case = LLMTestCase(
        input=case.input,
        actual_output=output.actual_output,
        expected_output=case.expected_output,
        retrieval_context=output.retrieval_context,
    )

    assert_test(test_case, generation_metrics(eval_config))

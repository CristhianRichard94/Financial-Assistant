"""End-to-end evals: the full golden dataset, all metrics.

Parametrized over every case in golden/dataset.yaml (no tag filter), running
the real retrieval + generation pipeline and scoring it against all five
metrics (contextual precision/recall/relevancy + faithfulness/answer
relevancy). This is the suite `deepeval test run` is meant to be pointed at
for a full quality report; test_retrieval_quality.py and
test_generation_quality.py exist separately for faster, targeted runs during
iteration (e.g. `pytest evals -k retrieval`).
"""

from __future__ import annotations

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from rag_eval.dataset import load_golden_cases
from rag_eval.metrics import all_metrics
from rag_eval.pipeline_runner import run_pipeline


@pytest.mark.parametrize(
    "case", load_golden_cases(), ids=lambda case: case.id
)
def test_end_to_end(case, eval_config):
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
        expected_retrieval_context=case.expected_retrieval_context,
    )

    assert_test(test_case, all_metrics(eval_config))

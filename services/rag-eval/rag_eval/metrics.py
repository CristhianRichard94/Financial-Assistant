"""DeepEval metric instances used across the eval suite.

All metrics are judged by an OpenAI `GPTModel`, reusing this repo's existing
`OPENAI_API_KEY` (the only LLM provider already configured here) rather than
adding a new one. The judge model defaults to `gpt-5` and is configurable via
`DEEPEVAL_JUDGE_MODEL` (see rag_eval/config.py).

Thresholds are tuned here in one place so all three test modules
(test_retrieval_quality.py, test_generation_quality.py, test_end_to_end.py)
and scripts/run_evals.py stay consistent.
"""

from __future__ import annotations

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.models import OpenAIModel

from rag_eval.config import EvalConfig

# Default pass threshold applied to every metric below. 0.7 is DeepEval's own
# documented default for these metrics; kept explicit here rather than
# relying on each metric class's own default, so a future DeepEval version
# bump can't silently change eval behavior.
DEFAULT_THRESHOLD = 0.7


def build_judge_model(config: EvalConfig) -> OpenAIModel:
    """Build the OpenAI judge model shared by every metric below.

    Uses DeepEval's `OpenAIModel` (the non-deprecated successor to
    `GPTModel`), reusing this repo's own `OPENAI_API_KEY` rather than relying
    on DeepEval's separate API-key configuration/login flow.
    """
    return OpenAIModel(model=config.judge_model, api_key=config.openai_api_key)


def retrieval_metrics(config: EvalConfig, threshold: float = DEFAULT_THRESHOLD) -> list:
    """Metrics that score retrieval quality: are the right chunks found
    (precision), is nothing relevant missing (recall), and is the retrieved
    context actually relevant to the question (relevancy)?
    """
    judge = build_judge_model(config)
    return [
        ContextualPrecisionMetric(threshold=threshold, model=judge, include_reason=True),
        ContextualRecallMetric(threshold=threshold, model=judge, include_reason=True),
        ContextualRelevancyMetric(threshold=threshold, model=judge, include_reason=True),
    ]


def generation_metrics(config: EvalConfig, threshold: float = DEFAULT_THRESHOLD) -> list:
    """Metrics that score generation quality: does the answer stick to the
    retrieved excerpts (faithfulness) and does it actually answer the
    question (answer relevancy)?
    """
    judge = build_judge_model(config)
    return [
        FaithfulnessMetric(threshold=threshold, model=judge, include_reason=True),
        AnswerRelevancyMetric(threshold=threshold, model=judge, include_reason=True),
    ]


def all_metrics(config: EvalConfig, threshold: float = DEFAULT_THRESHOLD) -> list:
    """All retrieval + generation metrics, used by the end-to-end suite."""
    return retrieval_metrics(config, threshold) + generation_metrics(config, threshold)

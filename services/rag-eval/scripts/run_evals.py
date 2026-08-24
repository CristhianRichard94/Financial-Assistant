#!/usr/bin/env python3
"""Standalone DeepEval runner for the golden dataset - no pytest ceremony.

Runs the real retrieval + generation pipeline for every case in
golden/dataset.yaml, scores it with all metrics via `deepeval.evaluate()`,
and prints a summary table. Useful for a quick manual sanity check without
invoking pytest/deepeval's test-runner wrapper.

Requires real OPENAI_API_KEY, SUPABASE_URL, and SUPABASE_SERVICE_KEY (see
../.env.example), plus the sample corpus already ingested for EVAL_USER_ID
(see ../golden/README.md). If credentials are missing, this prints a clear
message instead of a raw traceback.

Usage:
    pip install -e ".[dev]"
    python scripts/run_evals.py
    python scripts/run_evals.py --tag retrieval   # only cases tagged "retrieval"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script directly without requiring the package to
# already be on sys.path (matches the convention used by
# services/rag-pipeline/scripts/test_ingest_and_query.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deepeval import evaluate
from deepeval.test_case import LLMTestCase

from rag_eval.config import MissingEnvironmentVariable, load_eval_config
from rag_eval.dataset import InvalidGoldenDataset, filter_by_tag, load_golden_cases
from rag_eval.metrics import all_metrics
from rag_eval.pipeline_runner import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default=None,
        help="Only run golden cases with this tag (e.g. 'retrieval', 'generation').",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_eval_config()
    except MissingEnvironmentVariable as error:
        print("Cannot run rag-eval: missing configuration.\n")
        print(f"  {error}\n")
        print(
            "Set OPENAI_API_KEY, SUPABASE_URL, and SUPABASE_SERVICE_KEY "
            "(see services/rag-eval/.env.example) and try again."
        )
        return 1

    try:
        cases = load_golden_cases()
    except InvalidGoldenDataset as error:
        print(f"Cannot load golden dataset: {error}")
        return 1

    if args.tag:
        cases = filter_by_tag(cases, args.tag)
        if not cases:
            print(f"No golden cases tagged '{args.tag}'.")
            return 1

    print(f"=== Running {len(cases)} golden case(s) against the real RAG pipeline ===\n")

    test_cases = []
    for case in cases:
        print(f"[{case.id}] {case.input}")
        try:
            output = run_pipeline(
                case.input,
                config.eval_user_id,
                date_from=case.date_from,
                date_to=case.date_to,
                document_type=case.document_type,
            )
        except Exception as error:  # noqa: BLE001 - surface any failure clearly
            print(f"  FAILED to run pipeline: {error}")
            continue
        test_cases.append(
            LLMTestCase(
                input=case.input,
                actual_output=output.actual_output,
                expected_output=case.expected_output,
                retrieval_context=output.retrieval_context,
                expected_retrieval_context=case.expected_retrieval_context,
            )
        )

    if not test_cases:
        print("\nNo test cases were successfully run.")
        return 1

    print(f"\n=== Scoring {len(test_cases)} case(s) with DeepEval ===\n")
    evaluate(test_cases, all_metrics(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

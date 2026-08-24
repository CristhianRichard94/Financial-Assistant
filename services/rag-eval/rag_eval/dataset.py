"""Loads golden evaluation cases from golden/dataset.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DATASET_PATH = Path(__file__).resolve().parent.parent / "golden" / "dataset.yaml"


class InvalidGoldenDataset(RuntimeError):
    """Raised when golden/dataset.yaml is missing required fields or malformed."""


@dataclass(frozen=True)
class GoldenCase:
    """One golden test case: a question plus enough expected context/answer
    to score both retrieval and generation quality against.
    """

    id: str
    input: str
    expected_output: str
    tags: list[str] = field(default_factory=list)
    document_type: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    # Optional list of substrings/snippets a good retrieval should surface,
    # used as DeepEval's `expected_retrieval_context` (ContextualRecallMetric
    # in particular needs this to score whether all relevant info was
    # retrieved). Falls back to `expected_output` itself if omitted, since a
    # correct answer generally implies the supporting excerpt was retrieved.
    expected_retrieval_context: list[str] = field(default_factory=list)


def _parse_case(raw: dict[str, Any]) -> GoldenCase:
    missing = [key for key in ("id", "input", "expected_output") if key not in raw]
    if missing:
        raise InvalidGoldenDataset(
            f"Golden case is missing required field(s) {missing}: {raw!r}"
        )
    expected_retrieval_context = raw.get("expected_retrieval_context") or [raw["expected_output"]]
    return GoldenCase(
        id=str(raw["id"]),
        input=str(raw["input"]),
        expected_output=str(raw["expected_output"]),
        tags=list(raw.get("tags") or []),
        document_type=raw.get("document_type"),
        date_from=raw.get("date_from"),
        date_to=raw.get("date_to"),
        expected_retrieval_context=[str(item) for item in expected_retrieval_context],
    )


def load_golden_cases(path: Path | str = DEFAULT_DATASET_PATH) -> list[GoldenCase]:
    """Load and validate all golden cases from a YAML file.

    Raises InvalidGoldenDataset with a human-readable message if the file is
    missing, empty, or a case is malformed, instead of failing deep inside
    generic YAML/KeyError machinery.
    """
    path = Path(path)
    if not path.exists():
        raise InvalidGoldenDataset(f"Golden dataset file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not raw or "cases" not in raw:
        raise InvalidGoldenDataset(
            f"Golden dataset file {path} must contain a top-level 'cases' list."
        )

    cases = [_parse_case(item) for item in raw["cases"]]
    if not cases:
        raise InvalidGoldenDataset(f"Golden dataset file {path} contains zero cases.")
    return cases


def filter_by_tag(cases: list[GoldenCase], tag: str) -> list[GoldenCase]:
    """Return only the cases tagged with `tag`."""
    return [case for case in cases if tag in case.tags]

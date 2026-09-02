"""Shared CSV loading and header matching for document parsers."""

from __future__ import annotations

import csv
from pathlib import Path


def read_csv(path: str | Path) -> tuple[list[str], list[dict[str, str | None]]]:
    """Read a UTF-8 CSV with BOM support and return headers plus data rows."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return reader.fieldnames or [], list(reader)


def find_column(fieldnames: list[str], candidates: list[str]) -> str | None:
    """Find a header by matching trimmed, case-insensitive names."""
    normalized = {name.strip().lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None

"""Parsing of source documents (PDF, CSV) into raw text."""

from __future__ import annotations

import csv
from pathlib import Path

from pypdf import PdfReader


def parse_pdf(path: Path) -> str:
    """Extract all text from a PDF, page by page.

    Pages that fail to yield any text (e.g. scanned image pages with no
    embedded text layer) contribute an empty string rather than raising,
    since pypdf's extract_text() already treats that case as empty output.
    """
    reader = PdfReader(str(path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages_text).strip()


def parse_csv(path: Path) -> str:
    """Render a CSV file as plain text, one line per row.

    Each row is rendered as "col1: val1 | col2: val2 | ..." using the header
    row as field names, which keeps row context inside a single chunk instead
    of relying on the model to infer column meaning from position alone.
    """
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        lines = []
        for row in reader:
            rendered = " | ".join(f"{key}: {value}" for key, value in row.items())
            lines.append(rendered)
    return "\n".join(lines).strip()


def parse_document(path: Path) -> str:
    """Parse a document based on its file extension.

    Supports .pdf and .csv. Raises ValueError for anything else.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".csv":
        return parse_csv(path)
    raise ValueError(f"Unsupported file type '{suffix}' for {path}. Supported: .pdf, .csv")

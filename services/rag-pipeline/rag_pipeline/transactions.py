"""Naive structured-transaction extraction from CSV bank exports.

Kept entirely separate from `parsing.parse_csv` (which flattens CSV rows into
one text blob per row for embedding/RAG retrieval - a completely different
purpose). This module extracts numeric/date fields so the dashboard can
compute real aggregates (income, spending, category breakdowns) from a
`transactions` table, without any embedding or LLM involvement.

Column matching is deliberately simple (case-insensitive header lookup
against a small set of common aliases) - there is no ML categorization here.
A CSV that doesn't look like a bank export at all (no recognizable date and
amount/debit/credit columns) yields an empty list rather than raising, since
not every uploaded CSV is expected to be a transaction export.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from rag_pipeline.csv_source import find_column, read_csv

_DATE_HEADERS = ["date", "transaction date", "posted date", "posting date"]
_DESCRIPTION_HEADERS = ["description", "memo", "name", "payee", "details"]
_CATEGORY_HEADERS = ["category", "type"]
_AMOUNT_HEADERS = ["amount", "transaction amount"]
_DEBIT_HEADERS = ["debit", "withdrawal"]
_CREDIT_HEADERS = ["credit", "deposit"]

_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"]

_DEFAULT_CATEGORY = "Uncategorized"


@dataclass(frozen=True)
class ParsedTransaction:
    occurred_on: date
    amount: float
    category: str
    description: str


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1]
    raw = raw.replace("$", "").replace(",", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return -abs(value) if negative else value


def parse_transactions_csv(path: str | Path) -> list[ParsedTransaction]:
    """Parse a CSV bank export into a list of `ParsedTransaction`.

    Returns `[]` (not an error) if the file has no recognizable date column,
    or no recognizable amount/debit-credit columns - i.e. it doesn't look
    like a transaction export at all. Individual rows missing a usable date
    or amount are silently skipped rather than failing the whole file.
    """
    fieldnames, rows = read_csv(path)
    if not fieldnames:
        return []

    date_col = find_column(fieldnames, _DATE_HEADERS)
    if date_col is None:
        return []

    amount_col = find_column(fieldnames, _AMOUNT_HEADERS)
    debit_col = find_column(fieldnames, _DEBIT_HEADERS)
    credit_col = find_column(fieldnames, _CREDIT_HEADERS)
    if amount_col is None and debit_col is None and credit_col is None:
        return []

    description_col = find_column(fieldnames, _DESCRIPTION_HEADERS)
    category_col = find_column(fieldnames, _CATEGORY_HEADERS)

    results: list[ParsedTransaction] = []
    for row in rows:
        occurred_on = _parse_date(row.get(date_col, "") or "")
        if occurred_on is None:
            continue

        amount: float | None = None
        if amount_col is not None:
            amount = _parse_amount(row.get(amount_col, "") or "")
        else:
            debit = _parse_amount(row.get(debit_col, "") or "") if debit_col else None
            credit = _parse_amount(row.get(credit_col, "") or "") if credit_col else None
            if debit is not None and credit is not None:
                amount = credit - abs(debit)
            elif debit is not None:
                amount = -abs(debit)
            elif credit is not None:
                amount = credit

        if amount is None:
            continue

        description = (row.get(description_col, "") or "").strip() if description_col else ""
        category = (row.get(category_col, "") or "").strip() if category_col else ""
        if not category:
            category = _DEFAULT_CATEGORY

        results.append(
            ParsedTransaction(
                occurred_on=occurred_on,
                amount=amount,
                category=category,
                description=description,
            )
        )

    return results

"""Tests for rag_pipeline.transactions.parse_transactions_csv."""

from __future__ import annotations

from datetime import date

from rag_pipeline.transactions import ParsedTransaction, parse_transactions_csv


def _write(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_parses_standard_headers(tmp_path):
    path = _write(
        tmp_path,
        "standard.csv",
        "Date,Description,Category,Amount\n"
        "2026-01-15,Coffee Shop,Dining,-4.50\n"
        "2026-01-16,Paycheck,Income,2000.00\n",
    )

    result = parse_transactions_csv(path)

    assert result == [
        ParsedTransaction(
            occurred_on=date(2026, 1, 15),
            amount=-4.50,
            category="Dining",
            description="Coffee Shop",
        ),
        ParsedTransaction(
            occurred_on=date(2026, 1, 16),
            amount=2000.00,
            category="Income",
            description="Paycheck",
        ),
    ]


def test_parses_alternate_headers_and_date_format(tmp_path):
    path = _write(
        tmp_path,
        "alt.csv",
        "Transaction Date,Memo,Type,Transaction Amount\n"
        "01/15/2026,Grocery Store,Groceries,-52.10\n",
    )

    result = parse_transactions_csv(path)

    assert len(result) == 1
    assert result[0].occurred_on == date(2026, 1, 15)
    assert result[0].amount == -52.10
    assert result[0].category == "Groceries"
    assert result[0].description == "Grocery Store"


def test_parses_debit_credit_split_columns(tmp_path):
    path = _write(
        tmp_path,
        "debit_credit.csv",
        "Date,Description,Debit,Credit\n"
        "2026-02-01,Rent,1500.00,\n"
        "2026-02-02,Deposit,,500.00\n",
    )

    result = parse_transactions_csv(path)

    assert len(result) == 2
    assert result[0].amount == -1500.00
    assert result[1].amount == 500.00


def test_missing_category_defaults_to_uncategorized(tmp_path):
    path = _write(
        tmp_path,
        "no_category.csv",
        "Date,Description,Amount\n2026-03-01,Mystery charge,-10.00\n",
    )

    result = parse_transactions_csv(path)

    assert result[0].category == "Uncategorized"


def test_blank_category_defaults_to_uncategorized(tmp_path):
    path = _write(
        tmp_path,
        "blank_category.csv",
        "Date,Description,Category,Amount\n2026-03-01,Mystery charge,,-10.00\n",
    )

    result = parse_transactions_csv(path)

    assert result[0].category == "Uncategorized"


def test_parses_parenthesized_negative_amounts(tmp_path):
    path = _write(
        tmp_path,
        "parens.csv",
        "Date,Description,Amount\n2026-03-05,Fee,($12.34)\n",
    )

    result = parse_transactions_csv(path)

    assert result[0].amount == -12.34


def test_non_transaction_csv_returns_empty_list(tmp_path):
    path = _write(
        tmp_path,
        "not_transactions.csv",
        "First Name,Last Name,Email\nJane,Doe,jane@example.com\n",
    )

    result = parse_transactions_csv(path)

    assert result == []


def test_rows_missing_date_or_amount_are_skipped(tmp_path):
    path = _write(
        tmp_path,
        "partial.csv",
        "Date,Description,Amount\n"
        "2026-03-01,Good row,-10.00\n"
        ",Missing date,-5.00\n"
        "2026-03-03,Missing amount,\n",
    )

    result = parse_transactions_csv(path)

    assert len(result) == 1
    assert result[0].description == "Good row"


def test_amount_with_dollar_sign_and_commas(tmp_path):
    path = _write(
        tmp_path,
        "formatted.csv",
        "Date,Description,Amount\n2026-03-01,Big purchase,\"$1,234.56\"\n",
    )

    result = parse_transactions_csv(path)

    assert result[0].amount == 1234.56


def test_empty_csv_returns_empty_list(tmp_path):
    path = _write(tmp_path, "empty.csv", "")

    result = parse_transactions_csv(path)

    assert result == []

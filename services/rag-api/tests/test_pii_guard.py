"""Tests for the deterministic output PII/account-number guardrail in
rag_api.pii_guard."""

from __future__ import annotations

from rag_api.pii_guard import redact_sensitive_numbers

# Well-known Visa test card number that passes the Luhn checksum.
_VALID_CARD = "4111111111111111"


def test_redacts_full_card_number_no_separators():
    text = f"Your card number is {_VALID_CARD}."

    redacted = redact_sensitive_numbers(text)

    assert _VALID_CARD not in redacted
    assert "1111" in redacted  # last 4 digits preserved
    assert "*" in redacted


def test_redacts_full_card_number_with_dash_separators():
    text = "Your card number is 4111-1111-1111-1111 on file."

    redacted = redact_sensitive_numbers(text)

    assert "4111-1111-1111-1111" not in redacted
    assert redacted.strip().count("*") > 0
    assert "1111" in redacted


def test_redacts_full_card_number_with_space_separators():
    text = "Your card number is 4111 1111 1111 1111 on file."

    redacted = redact_sensitive_numbers(text)

    assert "4111 1111 1111 1111" not in redacted
    assert "*" in redacted


def test_redacts_ssn_like_pattern():
    text = "Your SSN on file is 123-45-6789."

    redacted = redact_sensitive_numbers(text)

    assert "123-45-6789" not in redacted
    assert "***-**-6789" in redacted


def test_does_not_redact_last_four_digit_mention():
    text = "Your card ending in 1111 was charged $42.50."

    redacted = redact_sensitive_numbers(text)

    assert redacted == text


def test_does_not_redact_dates():
    text = "Your statement covers transactions from 2024-01-01 to 2024-01-31."

    redacted = redact_sensitive_numbers(text)

    assert redacted == text


def test_does_not_redact_dollar_amounts():
    text = "You spent $1,234,567.89 across all your accounts this year."

    redacted = redact_sensitive_numbers(text)

    assert redacted == text


def test_does_not_redact_transaction_counts():
    text = "You made 128 transactions in the last 90 days."

    redacted = redact_sensitive_numbers(text)

    assert redacted == text


def test_does_not_redact_long_digit_sequence_failing_luhn_check():
    # A 16-digit sequence that does NOT pass the Luhn checksum - treated as
    # a non-card reference/invoice number, not redacted, to avoid
    # over-redacting legitimate long identifiers.
    non_luhn_sequence = "1234567890123456"

    text = f"Your invoice reference number is {non_luhn_sequence}."

    redacted = redact_sensitive_numbers(text)

    assert redacted == text


def test_no_op_on_empty_string():
    assert redact_sensitive_numbers("") == ""


def test_no_op_on_text_with_no_sensitive_patterns():
    text = "Your balance is $500 as of last Tuesday."

    assert redact_sensitive_numbers(text) == text

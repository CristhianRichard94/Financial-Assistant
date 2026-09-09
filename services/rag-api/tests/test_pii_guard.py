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


# --- Non-Luhn bank account number heuristic (issue #40) --------------------


def test_redacts_bank_account_number_near_account_keyword():
    # 10-digit account number, fails Luhn, but sits right next to "account".
    text = "Your bank account number is 4552981037."

    redacted = redact_sensitive_numbers(text)

    assert "4552981037" not in redacted
    assert "1037" in redacted  # last 4 digits preserved
    assert "*" in redacted


def test_redacts_short_account_number_near_acct_keyword():
    # 8-digit account number (below the card-Luhn 13-19 digit floor).
    text = "Please reference acct 12345678 for this transfer."

    redacted = redact_sensitive_numbers(text)

    assert "12345678" not in redacted
    assert "5678" in redacted


def test_redacts_account_number_near_routing_keyword():
    text = "Routing number 021000021, account 9988776655."

    redacted = redact_sensitive_numbers(text)

    assert "9988776655" not in redacted


def test_redacts_account_number_near_iban_keyword():
    text = "IBAN: 12345678901234"

    redacted = redact_sensitive_numbers(text)

    assert "12345678901234" not in redacted


def test_does_not_redact_unrelated_digit_run_without_context_keyword():
    # A 10-digit number with no nearby account/acct/iban/routing keyword -
    # must not be redacted, to avoid a false-positive flood over ordinary
    # long numbers (phone numbers, order numbers, etc.).
    text = "Your order confirmation number is 4552981037."

    redacted = redact_sensitive_numbers(text)

    assert redacted == text


def test_does_not_redact_short_unrelated_digit_run():
    text = "The reference code is 12345678 for your records."

    redacted = redact_sensitive_numbers(text)

    assert redacted == text


def test_account_heuristic_keyword_match_is_case_insensitive():
    text = "Your Account Number is 4552981037."

    redacted = redact_sensitive_numbers(text)

    assert "4552981037" not in redacted


def test_account_heuristic_does_not_double_redact_luhn_card_number():
    # A Luhn-valid 16-digit card number near the word "account" must still
    # go through the card-redaction path (grouped-in-4s masking), not be
    # additionally mangled by the account heuristic.
    text = f"Your account card number is {_VALID_CARD}."

    redacted = redact_sensitive_numbers(text)

    assert _VALID_CARD not in redacted
    assert "1111" in redacted
    assert redacted.count("*") == len(_VALID_CARD) - 4

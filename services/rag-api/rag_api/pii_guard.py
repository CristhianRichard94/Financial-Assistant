"""Output guardrail: redact raw PII/account-number-like patterns from
generated answers before they're returned to the caller.

This is a deterministic, regex/heuristic check - NOT another LLM call - run
as a final pass over `ask_openai`'s generated answer text (see
`rag_api/openai_client.py::ask_openai`). It exists because the system prompt
only instructs the model on cite/answer behavior; nothing before this
verified that the generated text doesn't needlessly surface more raw
sensitive digits than the question requires (full card numbers, SSN-like
patterns).

Deliberately redacts rather than blocks: a false positive on a redaction
degrades one substring of an otherwise-useful answer, whereas blocking the
whole response on a false positive throws away a correct, grounded answer
entirely. Blocking could be reconsidered for a stricter deployment (e.g. if
regulatory requirements mandate never emitting these patterns at all, even
partially before redaction), but for this assistant's use case (helping a
user understand their own uploaded documents) redaction is the safer
default without being overly disruptive.

Explicitly NOT guarded against (by design):
- Last-4-digit mentions (e.g. "ending in 1234") - these are short by
  construction and won't match the length-gated patterns below, so
  "what's the last 4 digits of my card" keeps working.
- Dates, transaction counts, dollar amounts - these don't form long
  contiguous digit runs of the length the patterns below require.
- Bank routing/account numbers beyond generic long-digit-sequence
  detection: nothing in this codebase's document/transaction storage
  identifies a distinct "routing number" pattern (no fixed-width field is
  modeled anywhere in rag_pipeline). These are additionally caught by the
  keyword-gated heuristic below (see `_redact_account_candidates`) when
  they sit near an account-ish keyword, on top of being caught incidentally
  by the card-Luhn path when they happen to look like a 13-19 digit
  card-like sequence and pass the Luhn check.
"""

from __future__ import annotations

import re

# Matches a run of 13-19 digits, allowing single spaces or dashes between
# digits (common card-number formatting: "4111 1111 1111 1111" or
# "4111-1111-1111-1111"), bounded so it doesn't match as a substring of a
# longer digit run. Length range covers real-world card number lengths
# (13-19 digits per ISO/IEC 7812).
_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")

# SSN-like pattern: XXX-XX-XXXX.
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")

# Matches a bare run of 8-19 digits (no separators), the same length floor
# used to reduce false positives on the card path but extended down to 8
# (real-world bank account numbers can be as short as 8 digits, well below
# the 13-19 digit card-number range) - deliberately NOT Luhn-gated, since
# real bank account/routing numbers have no checksum at all and would never
# pass the card path's Luhn check. Gated instead on nearby context keywords
# (see `_ACCOUNT_CONTEXT_KEYWORDS_RE`) to avoid redacting arbitrary
# unrelated long numbers (phone numbers, order numbers, reference codes).
_ACCOUNT_CANDIDATE_RE = re.compile(r"(?<!\d)\d{8,19}(?!\d)")

# Case-insensitive account-ish context keywords. Matched against a window of
# characters around a candidate digit run (see `_ACCOUNT_CONTEXT_WINDOW_CHARS`
# below), not the whole text, so a keyword appearing elsewhere in a long
# answer doesn't cause every unrelated digit run in that answer to be
# redacted.
_ACCOUNT_CONTEXT_KEYWORDS_RE = re.compile(r"\b(?:account|acct|iban|routing)\b", re.IGNORECASE)

# Characters of context scanned on each side of a candidate digit run when
# looking for an account-ish keyword. Wide enough to cover typical phrasing
# ("Your bank account number is ...", "Routing number ..., account ...")
# without being so wide it starts picking up unrelated keywords from
# elsewhere in a paragraph.
_ACCOUNT_CONTEXT_WINDOW_CHARS = 40


def _luhn_checksum(digits: str) -> bool:
    """Standard Luhn (mod 10) checksum, used to reduce false positives on
    long digit runs that aren't actually card numbers (e.g. arbitrary
    reference/invoice numbers)."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _redact_digits(digits: str) -> str:
    """Mask all but the last 4 digits, matching common financial-UX
    redaction conventions (e.g. "**** **** **** 1234")."""
    last4 = digits[-4:]
    masked = "*" * (len(digits) - 4) + last4
    # Re-group in 4s for readability, matching typical card-number display.
    groups = [masked[i : i + 4] for i in range(0, len(masked), 4)]
    return " ".join(groups)


def _redact_card_match(match: re.Match[str]) -> str:
    raw = match.group(0)
    digits = re.sub(r"[ -]", "", raw)
    if not _luhn_checksum(digits):
        # Fails the checksum: very likely not an actual card/account
        # number (e.g. a long invoice/reference id) - leave it as-is to
        # avoid over-redacting legitimate content.
        return raw
    return _redact_digits(digits)


def _redact_ssn_match(match: re.Match[str]) -> str:
    digits = match.group(0).replace("-", "")
    last4 = digits[-4:]
    return f"***-**-{last4}"


def _redact_account_digits(digits: str) -> str:
    """Mask all but the last 4 digits of a bare (unformatted) account-like
    digit run, with no grouping/spacing.

    Deliberately not `_redact_digits` (used by the card path): that helper
    re-groups the masked output in 4s from the start, which for a run whose
    length isn't a multiple of 4 (account numbers, unlike card numbers, have
    no conventional fixed length) can split the preserved last 4 digits
    across two groups (e.g. "**10 37" instead of keeping "1037" together).
    """
    last4 = digits[-4:]
    return "*" * (len(digits) - 4) + last4


def _redact_account_candidates(text: str) -> str:
    """Redact 8-19 digit runs in `text` that sit near an account-ish
    keyword (see `_ACCOUNT_CONTEXT_KEYWORDS_RE`), regardless of Luhn
    checksum - this is additive to (and runs after) the card-Luhn path, so
    it only ever sees digit runs the card path didn't already redact (a
    Luhn-valid card number is already masked into a non-digit-run by that
    point) or chose to leave alone (a Luhn-invalid 13-19 digit run, still
    present as raw digits, is caught here too if it has account-ish
    context).
    """

    def _replace(match: re.Match[str]) -> str:
        if not _ACCOUNT_CONTEXT_KEYWORDS_RE.search(
            text[
                max(0, match.start() - _ACCOUNT_CONTEXT_WINDOW_CHARS) : match.start()
            ]
        ) and not _ACCOUNT_CONTEXT_KEYWORDS_RE.search(
            text[match.end() : match.end() + _ACCOUNT_CONTEXT_WINDOW_CHARS]
        ):
            # No account-ish keyword in the surrounding window: leave this
            # digit run alone, to avoid over-redacting unrelated long
            # numbers (phone numbers, order numbers, reference codes).
            return match.group(0)
        return _redact_account_digits(match.group(0))

    return _ACCOUNT_CANDIDATE_RE.sub(_replace, text)


def redact_sensitive_numbers(text: str) -> str:
    """Redact full card/account-number-like and SSN-like digit sequences in
    `text`, returning the redacted text.

    Safe to call on any answer text, including ones with no matches (a
    no-op in that case). See module docstring for exactly what is and
    isn't detected.
    """
    if not text:
        return text
    text = _SSN_RE.sub(_redact_ssn_match, text)
    text = _CARD_CANDIDATE_RE.sub(_redact_card_match, text)
    text = _redact_account_candidates(text)
    return text

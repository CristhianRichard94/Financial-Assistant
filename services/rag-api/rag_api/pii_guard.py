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
  modeled anywhere in rag_pipeline), so those are only caught incidentally
  if they happen to look like a 13-19 digit card-like sequence and pass the
  Luhn check below.
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
    return text

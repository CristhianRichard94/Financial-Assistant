"""Tests for rag_pipeline.retry's Supabase retry/backoff wrapper."""

from __future__ import annotations

import time

import httpx
import pytest
from postgrest.exceptions import APIError

from rag_pipeline.retry import execute_with_retry, with_retry


class _FakeBuilder:
    """Stand-in for a postgrest-py query builder whose `.execute()` fails a
    fixed number of times before succeeding (or never succeeds)."""

    def __init__(self, exceptions_then_success):
        # A list of exceptions to raise, in order, one per call. Once
        # exhausted, `.execute()` returns "success".
        self._exceptions = list(exceptions_then_success)
        self.call_count = 0

    def execute(self):
        self.call_count += 1
        if self._exceptions:
            raise self._exceptions.pop(0)
        return "success"


def _api_error(code) -> APIError:
    return APIError({"message": "boom", "code": code, "hint": None, "details": None})


class TestTransientErrorsRetrySucceed:
    def test_succeeds_on_second_attempt_after_timeout(self):
        builder = _FakeBuilder([httpx.ConnectTimeout("timed out")])

        result = execute_with_retry(builder)

        assert result == "success"
        assert builder.call_count == 2

    def test_succeeds_on_third_attempt_after_two_transient_errors(self):
        builder = _FakeBuilder(
            [httpx.ConnectError("conn refused"), _api_error(503)]
        )

        result = execute_with_retry(builder)

        assert result == "success"
        assert builder.call_count == 3

    def test_retries_on_429_rate_limit(self):
        builder = _FakeBuilder([_api_error(429)])

        result = execute_with_retry(builder)

        assert result == "success"
        assert builder.call_count == 2



class TestNonTransientErrorsFailFast:
    def test_does_not_retry_structured_postgrest_error(self):
        # A structured PostgREST/Postgres error code (a str, not an int
        # HTTP status) - e.g. a Postgres SQLSTATE unique-violation code,
        # which happens to look numeric but is not an HTTP status - never
        # transient. See rag_pipeline/retry.py's `_status_code_from_api_error`.
        builder = _FakeBuilder([_api_error("23505")])

        with pytest.raises(APIError):
            execute_with_retry(builder)

        assert builder.call_count == 1

    def test_does_not_retry_4xx_status(self):
        builder = _FakeBuilder([_api_error(404)])

        with pytest.raises(APIError):
            execute_with_retry(builder)

        assert builder.call_count == 1

    def test_does_not_retry_arbitrary_value_error(self):
        builder = _FakeBuilder([ValueError("not a supabase error at all")])

        with pytest.raises(ValueError):
            execute_with_retry(builder)

        assert builder.call_count == 1


class TestRetriesExhausted:
    def test_exhausted_retries_reraise_original_error_type(self):
        # Always-failing transient error: retries exhaust and the original
        # exception type propagates unchanged, so existing callers (e.g.
        # rag_api routes turning this into a 502 fallback) keep working.
        builder = _FakeBuilder([_api_error(500)] * 10)

        with pytest.raises(APIError):
            execute_with_retry(builder)

        # Capped at 3 attempts total (1 initial + 2 retries).
        assert builder.call_count == 3


class TestTimeBudget:
    def test_total_retry_time_is_bounded(self):
        """Even if every attempt fails transiently, the whole call must not
        hang: it must return control (by raising) within a small, bounded
        amount of wall-clock time rather than retrying indefinitely."""
        builder = _FakeBuilder([_api_error(500)] * 100)

        start = time.monotonic()
        with pytest.raises(APIError):
            execute_with_retry(builder)
        elapsed = time.monotonic() - start

        # Generous upper bound (stop_after_attempt(3) + stop_after_delay(8)
        # in rag_pipeline/retry.py caps this well under this) - this asserts
        # the call doesn't hang, not the exact backoff timing.
        assert elapsed < 15


class TestWithRetryHelper:
    def test_with_retry_wraps_arbitrary_callable(self):
        state = {"calls": 0}

        def _flaky():
            state["calls"] += 1
            if state["calls"] < 2:
                raise httpx.ReadTimeout("slow")
            return "ok"

        assert with_retry(_flaky) == "ok"
        assert state["calls"] == 2

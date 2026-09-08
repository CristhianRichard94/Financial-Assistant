"""Tests for rag_api.tracing: Langfuse client construction, trace/generation
recording, and the fail-open guarantees required of every function here.

Tracing must never be the reason a request fails, blocks, or leaks a
secret - every test class below maps onto one of those guarantees.
"""

from __future__ import annotations

import datetime as dt

import pytest

import rag_api.tracing as tracing_module
from rag_api.config import RagApiSettings
from rag_api.tracing import TraceContext


def _settings(**overrides) -> RagApiSettings:
    defaults = dict(openai_api_key="sk-test-key", internal_api_key="test-internal-api-key")
    defaults.update(overrides)
    return RagApiSettings(**defaults)


def _traced_settings(**overrides) -> RagApiSettings:
    defaults = dict(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-lf-test",
    )
    defaults.update(overrides)
    return _settings(**defaults)


@pytest.fixture(autouse=True)
def _reset_cached_client():
    tracing_module._client = None
    tracing_module._client_key = None
    yield
    tracing_module._client = None
    tracing_module._client_key = None


class TestGetLangfuseClientDisabledByDefault:
    def test_missing_both_keys_returns_none_without_constructing_client(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        client = tracing_module._get_langfuse_client(_settings())

        assert client is None
        mock_langfuse_cls.assert_not_called()

    def test_missing_secret_key_only_returns_none(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        client = tracing_module._get_langfuse_client(
            _settings(langfuse_public_key="pk-test")
        )

        assert client is None
        mock_langfuse_cls.assert_not_called()

    def test_missing_public_key_only_returns_none(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        client = tracing_module._get_langfuse_client(
            _settings(langfuse_secret_key="sk-lf-test")
        )

        assert client is None
        mock_langfuse_cls.assert_not_called()


class TestGetLangfuseClientConfigured:
    def test_both_keys_set_constructs_client_with_host(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        tracing_module._get_langfuse_client(_traced_settings(langfuse_host="https://lf.example.com"))

        _, kwargs = mock_langfuse_cls.call_args
        assert kwargs["public_key"] == "pk-test"
        assert kwargs["secret_key"] == "sk-lf-test"
        assert kwargs["host"] == "https://lf.example.com"

    def test_client_is_cached_across_calls_with_same_settings(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        settings = _traced_settings()
        first = tracing_module._get_langfuse_client(settings)
        second = tracing_module._get_langfuse_client(settings)

        assert first is second
        mock_langfuse_cls.assert_called_once()

    def test_client_construction_failure_fails_open(self, mocker):
        mocker.patch("rag_api.tracing.Langfuse", side_effect=RuntimeError("network down"))

        client = tracing_module._get_langfuse_client(_traced_settings())

        assert client is None


class TestStartTraceFailOpen:
    def test_unconfigured_settings_returns_none(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        result = tracing_module.start_trace(_settings(), name="agent_query")

        assert result is None
        mock_langfuse_cls.assert_not_called()

    def test_configured_settings_returns_trace_context(self, mocker):
        mock_client = mocker.Mock()
        mock_client.trace.return_value = mocker.Mock(id="trace-123")
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)

        result = tracing_module.start_trace(
            _traced_settings(), name="agent_query", user_id="u1", session_id="conv1"
        )

        assert result == TraceContext(trace_id="trace-123")
        _, kwargs = mock_client.trace.call_args
        assert kwargs["name"] == "agent_query"
        assert kwargs["user_id"] == "u1"
        assert kwargs["session_id"] == "conv1"

    def test_trace_call_raising_fails_open(self, mocker):
        mock_client = mocker.Mock()
        mock_client.trace.side_effect = RuntimeError("timeout")
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)

        result = tracing_module.start_trace(_traced_settings(), name="agent_query")

        assert result is None


class TestRecordGenerationFailOpen:
    def test_unconfigured_settings_is_a_no_op(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        tracing_module.record_generation(
            _settings(),
            None,
            name="ask_openai",
            model="gpt-5",
            input_messages=[{"role": "user", "content": "hi"}],
            start_time=dt.datetime.now(dt.timezone.utc),
            end_time=dt.datetime.now(dt.timezone.utc),
            output="answer",
        )

        mock_langfuse_cls.assert_not_called()

    def test_configured_settings_records_generation_with_trace_id(self, mocker):
        mock_client = mocker.Mock()
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)
        start = dt.datetime.now(dt.timezone.utc)
        end = start + dt.timedelta(milliseconds=5)

        tracing_module.record_generation(
            _traced_settings(),
            TraceContext(trace_id="trace-abc"),
            name="ask_openai",
            model="gpt-5",
            input_messages=[{"role": "user", "content": "hi"}],
            start_time=start,
            end_time=end,
            output="answer text",
            usage={"input": 10, "output": 5, "total": 15},
        )

        mock_client.generation.assert_called_once()
        _, kwargs = mock_client.generation.call_args
        assert kwargs["trace_id"] == "trace-abc"
        assert kwargs["model"] == "gpt-5"
        assert kwargs["output"] == "answer text"
        assert kwargs["usage_details"] == {"input": 10, "output": 5, "total": 15}
        assert kwargs["start_time"] == start
        assert kwargs["end_time"] == end

    def test_no_trace_context_still_records_a_standalone_generation(self, mocker):
        """ask_openai/check_groundedness called outside the agent graph (the
        plain /query route) pass trace_context=None - this must still
        produce a generation (its own implicit trace), not be skipped."""
        mock_client = mocker.Mock()
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)

        tracing_module.record_generation(
            _traced_settings(),
            None,
            name="ask_openai",
            model="gpt-5",
            input_messages=[{"role": "user", "content": "hi"}],
            start_time=dt.datetime.now(dt.timezone.utc),
            end_time=dt.datetime.now(dt.timezone.utc),
            output="answer",
        )

        mock_client.generation.assert_called_once()
        _, kwargs = mock_client.generation.call_args
        assert "trace_id" not in kwargs

    def test_generation_call_raising_fails_open(self, mocker):
        mock_client = mocker.Mock()
        mock_client.generation.side_effect = RuntimeError("submit failed")
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)

        # Must not raise.
        tracing_module.record_generation(
            _traced_settings(),
            None,
            name="ask_openai",
            model="gpt-5",
            input_messages=[],
            start_time=dt.datetime.now(dt.timezone.utc),
            end_time=dt.datetime.now(dt.timezone.utc),
        )

    def test_error_status_is_recorded_without_raising(self, mocker):
        mock_client = mocker.Mock()
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)

        tracing_module.record_generation(
            _traced_settings(),
            None,
            name="ask_openai",
            model="gpt-5",
            input_messages=[],
            start_time=dt.datetime.now(dt.timezone.utc),
            end_time=dt.datetime.now(dt.timezone.utc),
            level="ERROR",
            status_message="AnswerRefusalError: content_filter",
        )

        _, kwargs = mock_client.generation.call_args
        assert kwargs["level"] == "ERROR"
        assert kwargs["status_message"] == "AnswerRefusalError: content_filter"


class TestUpdateTraceFailOpen:
    def test_no_trace_context_is_a_no_op(self, mocker):
        mock_langfuse_cls = mocker.patch("rag_api.tracing.Langfuse")

        tracing_module.update_trace(_traced_settings(), None, output={"answer": "x"})

        mock_langfuse_cls.assert_not_called()

    def test_updates_existing_trace_by_id(self, mocker):
        mock_client = mocker.Mock()
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)

        tracing_module.update_trace(
            _traced_settings(),
            TraceContext(trace_id="trace-xyz"),
            output={"answer": "final"},
        )

        mock_client.trace.assert_called_once()
        _, kwargs = mock_client.trace.call_args
        assert kwargs["id"] == "trace-xyz"
        assert kwargs["output"] == {"answer": "final"}

    def test_update_call_raising_fails_open(self, mocker):
        mock_client = mocker.Mock()
        mock_client.trace.side_effect = RuntimeError("timeout")
        mocker.patch("rag_api.tracing.Langfuse", return_value=mock_client)

        tracing_module.update_trace(
            _traced_settings(), TraceContext(trace_id="trace-xyz"), output={}
        )


class TestNoSecretsInTracingCalls:
    """rag_api.tracing itself never touches settings.openai_api_key,
    agent_checkpoint_db_url, or internal_api_key - it only ever reads the
    langfuse_* fields off RagApiSettings. This is a static guard against a
    future edit accidentally threading a secret-bearing field into a
    Langfuse call.
    """

    def test_tracing_module_source_never_accesses_secret_fields(self):
        import inspect

        source = inspect.getsource(tracing_module)
        for forbidden in ("openai_api_key", "agent_checkpoint_db_url", "internal_api_key"):
            assert f"settings.{forbidden}" not in source

"""Tests for prompt construction and answer synthesis in rag_api.openai_client."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from rag_pipeline.search import SearchResult

import rag_api.openai_client as openai_client_module
from rag_api.config import RagApiSettings
from rag_api.openai_client import (
    AnswerRefusalError,
    EmptyAnswerError,
    ask_openai,
    build_prompt,
    check_groundedness,
    get_client,
)


def _make_result(**overrides):
    defaults = dict(
        chunk_text="Some chunk of text.",
        chunk_metadata={"token_count": 42},
        filename="statement.pdf",
        similarity=0.87,
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


def _settings() -> RagApiSettings:
    return RagApiSettings(
        openai_api_key="sk-test-key",
        internal_api_key="test-internal-api-key",
    )


def _make_chat_response(content: str | None, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


def test_build_prompt_escapes_quotes_in_filename():
    result = _make_result(filename='foo.pdf"><script>alert(1)</script>')

    prompt = build_prompt("What did I spend?", [result])

    # The filename must never be able to close the source="..." attribute
    # or open a new tag inside the <excerpt> element.
    assert '"><script>' not in prompt
    assert "<script>" not in prompt
    assert '"' not in prompt.split('source="', 1)[1].split('"', 1)[0]


def test_build_prompt_strips_angle_brackets_from_filename():
    result = _make_result(filename="report<b>bold</b>.pdf")

    prompt = build_prompt("What did I spend?", [result])

    assert "<b>" not in prompt
    assert "</b>" not in prompt
    assert "<" not in prompt.split('source="', 1)[1].split('"', 1)[0]
    assert ">" not in prompt.split('source="', 1)[1].split('"', 1)[0]


def test_build_prompt_keeps_normal_filename_intact():
    result = _make_result(filename="bank_statement_may2025.pdf")

    prompt = build_prompt("What did I spend?", [result])

    assert 'source="bank_statement_may2025.pdf"' in prompt


class TestGetClientRetryConfig:
    """openai-python already retries transient errors (timeouts, connection
    errors, 429, 5xx) itself with backoff+jitter, and never retries 4xx - see
    rag_api/openai_client.py's module-level comment above `get_client`. This
    just verifies the client is actually constructed with a bounded timeout
    and explicit max_retries, rather than the library's very long defaults.
    """

    def test_get_client_sets_bounded_timeout_and_max_retries(self, mocker):
        openai_client_module._client = None
        mock_openai_cls = mocker.patch("rag_api.openai_client.OpenAI")

        get_client("sk-test-key")

        _, kwargs = mock_openai_cls.call_args
        assert kwargs["api_key"] == "sk-test-key"
        assert kwargs["max_retries"] == 2
        timeout = kwargs["timeout"]
        # A bounded read timeout well under openai-python's 600s default -
        # the exact value is an implementation detail, just assert it's sane.
        assert 0 < timeout.read <= 30
        openai_client_module._client = None


class TestAskOpenaiReasoningEffort:
    def test_ask_openai_passes_minimal_reasoning_effort(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "You spent $50."
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        ask_openai("How much did I spend?", [_make_result()], _settings())

        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["reasoning_effort"] == "minimal"


class TestAskOpenaiEmptyContent:
    def test_ask_openai_raises_on_empty_string_content(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response("")
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        with pytest.raises(EmptyAnswerError):
            ask_openai("How much did I spend?", [_make_result()], _settings())

    def test_ask_openai_raises_on_none_content(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(None)
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        with pytest.raises(EmptyAnswerError):
            ask_openai("How much did I spend?", [_make_result()], _settings())

    def test_ask_openai_returns_answer_when_content_filter_not_triggered(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "You spent $50."
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        answer, _sources = ask_openai(
            "How much did I spend?", [_make_result()], _settings()
        )

        assert answer == "You spent $50."

    def test_ask_openai_still_raises_answer_refusal_on_content_filter(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            None, finish_reason="content_filter"
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        with pytest.raises(AnswerRefusalError):
            ask_openai("How much did I spend?", [_make_result()], _settings())


class TestAskOpenaiPiiRedaction:
    """End-to-end coverage of the pii_guard redaction integrated into
    ask_openai, not just the regex in isolation (see rag_api.pii_guard)."""

    def test_ask_openai_redacts_full_card_number_in_generated_answer(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "Your card number on file is 4111111111111111."
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        answer, _sources = ask_openai(
            "What's my card number?", [_make_result()], _settings()
        )

        assert "4111111111111111" not in answer
        assert "1111" in answer

    def test_ask_openai_redacts_ssn_like_pattern_in_generated_answer(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "The SSN listed on this document is 123-45-6789."
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        answer, _sources = ask_openai(
            "What's the SSN on this document?", [_make_result()], _settings()
        )

        assert "123-45-6789" not in answer
        assert "***-**-6789" in answer

    def test_ask_openai_does_not_redact_last_four_digit_mention(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "The last 4 digits of your card are 1111."
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        answer, _sources = ask_openai(
            "What's the last 4 digits of my card?", [_make_result()], _settings()
        )

        assert answer == "The last 4 digits of your card are 1111."

    def test_ask_openai_does_not_redact_dates_or_amounts(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            "Between 2024-01-01 and 2024-01-31, you spent $1,234.56 across 12 transactions."
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        answer, _sources = ask_openai(
            "How much did I spend in January?", [_make_result()], _settings()
        )

        assert answer == (
            "Between 2024-01-01 and 2024-01-31, you spent $1,234.56 across 12 transactions."
        )


class TestCheckGroundednessReasoningEffort:
    def test_check_groundedness_passes_minimal_reasoning_effort(self, mocker):
        mock_client = mocker.Mock()
        payload = {"grounded": True, "issues": ""}
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        check_groundedness(
            "How much did I spend?", "You spent $50.", [_make_result()], _settings()
        )

        _, kwargs = mock_client.chat.completions.create.call_args
        assert kwargs["reasoning_effort"] == "minimal"


class TestCheckGroundednessEmptyContent:
    def test_check_groundedness_fails_open_on_empty_content(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        result = check_groundedness(
            "How much did I spend?", "You spent $50.", [_make_result()], _settings()
        )

        assert result.grounded is True

    def test_check_groundedness_fails_open_on_none_content(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        result = check_groundedness(
            "How much did I spend?", "You spent $50.", [_make_result()], _settings()
        )

        assert result.grounded is True

    def test_check_groundedness_fails_open_on_whitespace_only_content(self, mocker):
        mock_client = mocker.Mock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="   \n"))]
        )
        mocker.patch("rag_api.openai_client.get_client", return_value=mock_client)

        result = check_groundedness(
            "How much did I spend?", "You spent $50.", [_make_result()], _settings()
        )

        assert result.grounded is True

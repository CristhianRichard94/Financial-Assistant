"""Tests for rag_api.query_parser: OpenAI-backed query parsing, fail-open on error."""

from __future__ import annotations

import json
from types import SimpleNamespace

from rag_api.config import RagApiSettings
from rag_api.query_parser import ParsedQuery, parse_query


def _settings() -> RagApiSettings:
    return RagApiSettings(
        openai_api_key="sk-test-key",
        internal_api_key="test-internal-api-key",
    )


def _make_openai_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
        ]
    )


def test_parse_query_returns_parsed_query_on_valid_response(mocker):
    payload = {
        "rewritten_query": "account balance checking account March 2026",
        "intent": "lookup",
        "date_from": "2026-03-01",
        "date_to": "2026-03-31",
        "document_type": "pdf",
        "entities": ["checking account"],
    }
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _make_openai_response(payload)
    mocker.patch("rag_api.query_parser.get_client", return_value=mock_client)

    result = parse_query("What was my checking account balance in March?", _settings())

    assert result == ParsedQuery(
        rewritten_query="account balance checking account March 2026",
        intent="lookup",
        date_from="2026-03-01",
        date_to="2026-03-31",
        document_type="pdf",
        entities=["checking account"],
    )


def test_parse_query_out_of_scope_intent(mocker):
    payload = {
        "rewritten_query": "how does the stock market work",
        "intent": "out_of_scope",
        "date_from": None,
        "date_to": None,
        "document_type": None,
        "entities": [],
    }
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _make_openai_response(payload)
    mocker.patch("rag_api.query_parser.get_client", return_value=mock_client)

    result = parse_query("How does the stock market work?", _settings())

    assert result.intent == "out_of_scope"


def test_parse_query_fails_open_on_api_error(mocker):
    mocker.patch(
        "rag_api.query_parser.get_client",
        side_effect=RuntimeError("openai down"),
    )

    result = parse_query("How much did I spend on groceries?", _settings())

    assert result == ParsedQuery(
        rewritten_query="How much did I spend on groceries?", intent="lookup"
    )


def test_parse_query_fails_open_on_malformed_json(mocker):
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
    )
    mocker.patch("rag_api.query_parser.get_client", return_value=mock_client)

    result = parse_query("How much did I spend?", _settings())

    assert result == ParsedQuery(rewritten_query="How much did I spend?", intent="lookup")


def test_parse_query_fails_open_on_missing_required_field(mocker):
    payload = {
        "intent": "lookup",
        "date_from": None,
        "date_to": None,
        "document_type": None,
        "entities": [],
    }
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _make_openai_response(payload)
    mocker.patch("rag_api.query_parser.get_client", return_value=mock_client)

    result = parse_query("How much did I spend?", _settings())

    assert result == ParsedQuery(rewritten_query="How much did I spend?", intent="lookup")


def test_parse_query_fails_open_on_invalid_intent_value(mocker):
    payload = {
        "rewritten_query": "groceries spending",
        "intent": "not_a_real_intent",
        "date_from": None,
        "date_to": None,
        "document_type": None,
        "entities": [],
    }
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _make_openai_response(payload)
    mocker.patch("rag_api.query_parser.get_client", return_value=mock_client)

    result = parse_query("How much did I spend on groceries?", _settings())

    assert result == ParsedQuery(
        rewritten_query="How much did I spend on groceries?", intent="lookup"
    )

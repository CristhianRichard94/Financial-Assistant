"""Tests for /query/agent's multi-turn conversation memory (checkpointer)."""

from __future__ import annotations

from rag_pipeline.config import DEFAULT_MATCH_COUNT
from rag_pipeline.search import SearchResult

from rag_api.query_parser import ParsedQuery
from rag_api.schemas import SourceOut


def _make_result(**overrides):
    defaults = dict(
        chunk_text="Some chunk of text.",
        chunk_metadata={"token_count": 42},
        filename="statement.pdf",
        similarity=0.87,
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


def _make_parsed_query(**overrides) -> ParsedQuery:
    defaults = dict(
        rewritten_query="rewritten query",
        intent="lookup",
        date_from=None,
        date_to=None,
        document_type=None,
        entities=[],
    )
    defaults.update(overrides)
    return ParsedQuery(**defaults)


def _mock_happy_path(mocker, answer="An answer.", sources=None):
    mocker.patch(
        "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
    )
    mocker.patch("rag_pipeline.search", return_value=[_make_result()])
    ask_openai = mocker.patch(
        "rag_api.openai_client.ask_openai",
        return_value=(answer, sources if sources is not None else []),
    )
    return ask_openai


def test_agent_query_with_no_conversation_id_generates_one(client, mocker):
    _mock_happy_path(mocker)

    response = client.post("/query/agent", json={"question": "How much did I spend?"})

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert isinstance(body["conversation_id"], str)


def test_agent_query_second_call_sees_prior_turn_context(client, mocker):
    ask_openai = _mock_happy_path(mocker, answer="First answer.")

    first = client.post(
        "/query/agent", json={"question": "How much did I spend on groceries?"}
    )
    conversation_id = first.json()["conversation_id"]

    ask_openai.reset_mock()
    ask_openai.return_value = ("Second answer.", [])

    second = client.post(
        "/query/agent",
        json={"question": "And what about last month?", "conversation_id": conversation_id},
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    # The second call's ask_openai invocation should have received the
    # first turn's question/answer as prior history.
    _, kwargs = ask_openai.call_args
    history = kwargs["history"]
    assert {"role": "user", "content": "How much did I spend on groceries?"} in history
    assert {"role": "assistant", "content": "First answer."} in history


def test_agent_query_cross_user_same_conversation_id_does_not_leak_history(
    client, other_user_id, mocker
):
    """thread_id is `f"{user_id}:{conversation_id}"` (see run_agent_query in
    rag_api/agent/graph.py), not conversation_id alone, precisely so a
    different user supplying the same conversation_id can't see another
    user's history."""
    ask_openai = _mock_happy_path(mocker, answer="User A's answer.")

    first = client.post(
        "/query/agent", json={"question": "What is my account balance?"}
    )
    conversation_id = first.json()["conversation_id"]

    ask_openai.reset_mock()
    ask_openai.return_value = ("User B's answer.", [])

    other_client_response = client.post(
        "/query/agent",
        json={
            "question": "What is my account balance?",
            "conversation_id": conversation_id,
        },
        headers={"X-User-Id": other_user_id},
    )

    assert other_client_response.status_code == 200
    _, kwargs = ask_openai.call_args
    assert kwargs["history"] == []


def test_agent_query_different_conversation_id_does_not_see_unrelated_history(
    client, mocker
):
    ask_openai = _mock_happy_path(mocker, answer="First answer.")

    first = client.post(
        "/query/agent", json={"question": "How much did I spend on groceries?"}
    )
    first_conversation_id = first.json()["conversation_id"]
    assert first_conversation_id

    ask_openai.reset_mock()
    ask_openai.return_value = ("Unrelated answer.", [])

    # No conversation_id given -> a brand new one is generated, unrelated
    # to the first call's conversation.
    second = client.post(
        "/query/agent", json={"question": "Some other unrelated question?"}
    )

    assert second.status_code == 200
    second_conversation_id = second.json()["conversation_id"]
    assert second_conversation_id != first_conversation_id

    _, kwargs = ask_openai.call_args
    history = kwargs.get("history", [])
    assert history == []


def test_agent_query_returns_answer_and_sources(client, mocker):
    _mock_happy_path(
        mocker,
        answer="You spent $50 on groceries, according to statement.pdf.",
        sources=[SourceOut(filename="statement.pdf", similarity=0.87)],
    )

    response = client.post(
        "/query/agent", json={"question": "How much did I spend on groceries?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "You spent $50 on groceries, according to statement.pdf."
    assert body["sources"] == [{"filename": "statement.pdf", "similarity": 0.87}]


def test_agent_query_scopes_search_to_the_requesting_user(client, user_id, mocker):
    mocker.patch(
        "rag_api.query_parser.parse_query",
        return_value=_make_parsed_query(
            rewritten_query="rewritten: how much did I spend",
        ),
    )
    search = mocker.patch("rag_pipeline.search", return_value=[_make_result()])
    mocker.patch("rag_api.openai_client.ask_openai", return_value=("An answer.", []))

    client.post("/query/agent", json={"question": "How much did I spend?"})

    search.assert_called_once_with(
        "rewritten: how much did I spend",
        user_id,
        k=DEFAULT_MATCH_COUNT,
        date_from=None,
        date_to=None,
        document_type=None,
    )


def test_agent_query_short_circuits_for_out_of_scope_intent(client, mocker):
    mocker.patch(
        "rag_api.query_parser.parse_query",
        return_value=_make_parsed_query(intent="out_of_scope"),
    )
    search = mocker.patch("rag_pipeline.search")
    ask_openai = mocker.patch("rag_api.openai_client.ask_openai")

    response = client.post(
        "/query/agent", json={"question": "What's the weather today?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert body["answer"] == (
        "I can only answer questions about your uploaded financial documents."
    )
    search.assert_not_called()
    ask_openai.assert_not_called()


def test_agent_query_returns_502_on_search_error(client, mocker):
    mocker.patch(
        "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
    )
    mocker.patch("rag_pipeline.search", side_effect=RuntimeError("openai down"))

    response = client.post("/query/agent", json={"question": "What did I spend?"})

    assert response.status_code == 502

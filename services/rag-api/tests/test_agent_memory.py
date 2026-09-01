"""Tests for /query/agent's multi-turn conversation memory (checkpointer)."""

from __future__ import annotations

import pytest

from rag_pipeline.config import DEFAULT_MATCH_COUNT
from rag_pipeline.search import SearchResult

from rag_api import config as rag_api_config
from rag_api.agent import graph as agent_graph
from rag_api.openai_client import GroundednessResult
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


class TestGroundednessCritiqueLoop:
    """End-to-end tests for the critique loop wired into the /query/agent
    graph (parse -> retrieve -> generate -> critique -> ...). See
    rag_api/agent/nodes.py and rag_api/agent/graph.py.
    """

    def test_grounded_first_try_returns_answer_unchanged(self, client, mocker):
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        mocker.patch(
            "rag_api.openai_client.ask_openai",
            return_value=("A fully grounded answer.", []),
        )
        check_groundedness = mocker.patch(
            "rag_api.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=True, issues=""),
        )

        response = client.post(
            "/query/agent", json={"question": "How much did I spend?"}
        )

        assert response.status_code == 200
        assert response.json()["answer"] == "A fully grounded answer."
        check_groundedness.assert_called_once()

    def test_ungrounded_then_grounded_regenerates_once_with_feedback(
        self, client, mocker
    ):
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        ask_openai = mocker.patch(
            "rag_api.openai_client.ask_openai",
            side_effect=[
                ("An answer with an unsupported claim.", []),
                ("A corrected, grounded answer.", []),
            ],
        )
        mocker.patch(
            "rag_api.openai_client.check_groundedness",
            side_effect=[
                GroundednessResult(grounded=False, issues="Unsupported figure."),
                GroundednessResult(grounded=True, issues=""),
            ],
        )

        response = client.post(
            "/query/agent", json={"question": "How much did I spend?"}
        )

        assert response.status_code == 200
        assert response.json()["answer"] == "A corrected, grounded answer."
        assert ask_openai.call_count == 2
        _, second_call_kwargs = ask_openai.call_args_list[1]
        assert second_call_kwargs["critique_feedback"] == "Unsupported figure."

    def test_exhausted_retries_still_returns_an_answer_with_caveat(
        self, client, mocker
    ):
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        mocker.patch(
            "rag_api.openai_client.ask_openai",
            side_effect=[
                ("First attempt, ungrounded.", []),
                ("Second attempt, still ungrounded.", []),
            ],
        )
        mocker.patch(
            "rag_api.openai_client.check_groundedness",
            side_effect=[
                GroundednessResult(grounded=False, issues="Issue one."),
                GroundednessResult(grounded=False, issues="Issue two."),
            ],
        )

        response = client.post(
            "/query/agent", json={"question": "How much did I spend?"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["answer"].startswith("Second attempt, still ungrounded.")
        assert "could not be fully verified" in body["answer"]

    def test_out_of_scope_never_calls_groundedness_check(self, client, mocker):
        mocker.patch(
            "rag_api.query_parser.parse_query",
            return_value=_make_parsed_query(intent="out_of_scope"),
        )
        check_groundedness = mocker.patch("rag_api.openai_client.check_groundedness")

        response = client.post(
            "/query/agent", json={"question": "What's the weather?"}
        )

        assert response.status_code == 200
        check_groundedness.assert_not_called()


class TestCheckpointerBackendSelection:
    """Unit tests for `_get_checkpointer`'s choice between the SQLite
    fallback and the Postgres backend (see rag_api/agent/graph.py), without
    touching a live Postgres instance - `ConnectionPool`/`PostgresSaver` are
    patched at the point of use in `rag_api.agent.graph`.
    """

    def _make_settings(self, **overrides) -> rag_api_config.RagApiSettings:
        defaults = dict(
            openai_api_key="sk-test-key",
            internal_api_key="test-internal-api-key",
        )
        defaults.update(overrides)
        return rag_api_config.RagApiSettings(**defaults)

    def test_no_db_url_uses_sqlite_saver(self, tmp_path):
        """When AGENT_CHECKPOINT_DB_URL is unset, the graph still builds and
        runs via the sqlite path - this is what keeps local dev/pytest
        working with zero external dependencies."""
        settings = self._make_settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.sqlite")
        )

        checkpointer = agent_graph._get_checkpointer(settings)

        assert isinstance(checkpointer, agent_graph.SqliteSaver)

    def test_db_url_set_uses_postgres_saver(self, mocker):
        """When AGENT_CHECKPOINT_DB_URL is set, a PostgresSaver backed by a
        pooled connection is built instead of falling back to sqlite."""
        mock_pool_instance = mocker.MagicMock()
        mock_pool_cls = mocker.patch(
            "rag_api.agent.graph.ConnectionPool", return_value=mock_pool_instance
        )
        mock_saver_instance = mocker.MagicMock()
        mock_saver_cls = mocker.patch(
            "rag_api.agent.graph.PostgresSaver", return_value=mock_saver_instance
        )

        settings = self._make_settings(
            agent_checkpoint_db_url="postgresql://fake-user:fake-pass@fake-host:5432/fake-db"
        )

        checkpointer = agent_graph._get_checkpointer(settings)

        assert checkpointer is mock_saver_instance
        mock_pool_cls.assert_called_once()
        _, pool_kwargs = mock_pool_cls.call_args
        assert pool_kwargs["conninfo"] == settings.agent_checkpoint_db_url
        assert pool_kwargs["max_size"] == 5
        # autocommit + prepare_threshold=0 are required for compatibility
        # with Supabase's Supavisor pooler - see graph.py.
        assert pool_kwargs["kwargs"]["autocommit"] is True
        assert pool_kwargs["kwargs"]["prepare_threshold"] == 0
        mock_saver_cls.assert_called_once_with(mock_pool_instance)
        mock_saver_instance.setup.assert_called_once()

    def test_postgres_checkpointer_is_cached_across_calls(self, mocker):
        """Repeated calls with the same db_url must reuse the same pool and
        saver rather than opening a new pool per request."""
        mocker.patch("rag_api.agent.graph.ConnectionPool")
        mocker.patch("rag_api.agent.graph.PostgresSaver")

        settings = self._make_settings(
            agent_checkpoint_db_url="postgresql://fake-user:fake-pass@fake-host:5432/fake-db-cache-test"
        )

        first = agent_graph._get_checkpointer(settings)
        second = agent_graph._get_checkpointer(settings)

        assert first is second
        agent_graph.ConnectionPool.assert_called_once()
        agent_graph.PostgresSaver.assert_called_once()

    def test_setup_runs_under_a_postgres_advisory_lock(self, mocker):
        """`.setup()` must be sandwiched between pg_advisory_lock/unlock
        calls on a connection checked out from the pool, so two processes
        racing through first-time setup (e.g. an ECS rolling deploy running
        old and new tasks concurrently) serialize instead of both mutating
        the checkpoint_migrations table at once."""
        mock_conn = mocker.MagicMock()
        mock_pool_instance = mocker.MagicMock()
        mock_pool_instance.connection.return_value.__enter__.return_value = mock_conn
        mocker.patch(
            "rag_api.agent.graph.ConnectionPool", return_value=mock_pool_instance
        )
        mock_saver_instance = mocker.MagicMock()
        mocker.patch(
            "rag_api.agent.graph.PostgresSaver", return_value=mock_saver_instance
        )

        settings = self._make_settings(
            agent_checkpoint_db_url="postgresql://fake-user:fake-pass@fake-host:5432/fake-db-advisory-lock-test"
        )

        agent_graph._get_checkpointer(settings)

        assert mock_conn.execute.call_args_list[0][0][0] == "SELECT pg_advisory_lock(%s)"
        mock_saver_instance.setup.assert_called_once()
        assert (
            mock_conn.execute.call_args_list[-1][0][0]
            == "SELECT pg_advisory_unlock(%s)"
        )

    def test_setup_failure_closes_the_pool_and_does_not_cache_it(self, mocker):
        """If `.setup()` raises (e.g. a transient connectivity blip or
        migration error), the pool must be closed rather than leaked, and
        nothing must be cached - so a later call retries cleanly instead of
        reusing a half-initialized, uncached-but-still-open pool."""
        mock_pool_instance = mocker.MagicMock()
        mocker.patch(
            "rag_api.agent.graph.ConnectionPool", return_value=mock_pool_instance
        )
        mock_saver_instance = mocker.MagicMock()
        mock_saver_instance.setup.side_effect = RuntimeError("setup failed")
        mocker.patch(
            "rag_api.agent.graph.PostgresSaver", return_value=mock_saver_instance
        )

        settings = self._make_settings(
            agent_checkpoint_db_url="postgresql://fake-user:fake-pass@fake-host:5432/fake-db-setup-failure-test"
        )

        with pytest.raises(RuntimeError, match="setup failed"):
            agent_graph._get_checkpointer(settings)

        mock_pool_instance.close.assert_called_once()
        assert settings.agent_checkpoint_db_url not in agent_graph._postgres_checkpointers

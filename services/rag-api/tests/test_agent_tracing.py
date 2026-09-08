"""Tests for Langfuse tracing wired into the agentic query graph
(rag_api/agent/graph.py's run_agent_query/build_agent_graph). See
rag_api/tracing.py for the underlying fail-open Langfuse wrapper.
"""

from __future__ import annotations

from rag_pipeline.search import SearchResult

from rag_api.agent import graph as agent_graph
from rag_api.config import RagApiSettings
from rag_api.openai_client import GroundednessResult
from rag_api.query_parser import ParsedQuery
from rag_api.tracing import TraceContext


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


def _settings(**overrides) -> RagApiSettings:
    defaults = dict(openai_api_key="sk-test-key", internal_api_key="test-internal-api-key")
    defaults.update(overrides)
    return RagApiSettings(**defaults)


class TestRunAgentQueryTracing:
    def test_starts_one_trace_per_call(self, mocker, tmp_path):
        start_trace = mocker.patch(
            "rag_api.agent.graph.tracing.start_trace",
            return_value=TraceContext(trace_id="trace-1"),
        )
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        mocker.patch(
            "rag_api.openai_client.ask_openai", return_value=("An answer.", [])
        )
        mocker.patch(
            "rag_api.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=True, issues=""),
        )
        settings = _settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.sqlite")
        )

        agent_graph.run_agent_query("How much did I spend?", "user-1", "conv-1", settings)

        start_trace.assert_called_once()
        _, kwargs = start_trace.call_args
        assert kwargs["user_id"] == "user-1"
        assert kwargs["session_id"] == "conv-1"

    def test_generate_and_critique_nodes_share_the_same_trace_context(
        self, mocker, tmp_path
    ):
        """The single trace started for this run must be threaded into both
        generate_node's ask_openai call and critique_node's
        check_groundedness call, so both land as nested observations of
        the same trace rather than each starting its own."""
        trace_context = TraceContext(trace_id="trace-shared")
        mocker.patch(
            "rag_api.agent.graph.tracing.start_trace", return_value=trace_context
        )
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        ask_openai = mocker.patch(
            "rag_api.openai_client.ask_openai", return_value=("An answer.", [])
        )
        check_groundedness = mocker.patch(
            "rag_api.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=True, issues=""),
        )
        settings = _settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.sqlite")
        )

        agent_graph.run_agent_query("How much did I spend?", "user-1", "conv-1", settings)

        _, ask_kwargs = ask_openai.call_args
        assert ask_kwargs["trace_context"] is trace_context
        _, check_kwargs = check_groundedness.call_args
        assert check_kwargs["trace_context"] is trace_context

    def test_two_sequential_calls_for_the_same_conversation_start_two_traces(
        self, mocker, tmp_path
    ):
        """Trace-per-request, not trace-per-conversation: two separate
        run_agent_query calls sharing a conversation_id must each get their
        own trace, not be merged into one trace spanning both turns."""
        start_trace = mocker.patch(
            "rag_api.agent.graph.tracing.start_trace",
            side_effect=[
                TraceContext(trace_id="trace-turn-1"),
                TraceContext(trace_id="trace-turn-2"),
            ],
        )
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        mocker.patch(
            "rag_api.openai_client.ask_openai", return_value=("An answer.", [])
        )
        mocker.patch(
            "rag_api.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=True, issues=""),
        )
        settings = _settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.sqlite")
        )

        agent_graph.run_agent_query("First question?", "user-1", "conv-shared", settings)
        agent_graph.run_agent_query("Second question?", "user-1", "conv-shared", settings)

        assert start_trace.call_count == 2

    def test_updates_trace_with_final_answer_on_success(self, mocker, tmp_path):
        trace_context = TraceContext(trace_id="trace-1")
        mocker.patch(
            "rag_api.agent.graph.tracing.start_trace", return_value=trace_context
        )
        update_trace = mocker.patch("rag_api.agent.graph.tracing.update_trace")
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        mocker.patch(
            "rag_api.openai_client.ask_openai", return_value=("The final answer.", [])
        )
        mocker.patch(
            "rag_api.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=True, issues=""),
        )
        settings = _settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.sqlite")
        )

        agent_graph.run_agent_query("How much did I spend?", "user-1", "conv-1", settings)

        update_trace.assert_called_once()
        args, kwargs = update_trace.call_args
        assert args[1] is trace_context
        assert kwargs["output"]["answer"] == "The final answer."

    def test_updates_trace_with_error_status_when_graph_raises_then_still_raises(
        self, mocker, tmp_path
    ):
        trace_context = TraceContext(trace_id="trace-1")
        mocker.patch(
            "rag_api.agent.graph.tracing.start_trace", return_value=trace_context
        )
        update_trace = mocker.patch("rag_api.agent.graph.tracing.update_trace")
        mocker.patch(
            "rag_api.query_parser.parse_query",
            side_effect=RuntimeError("query parser exploded"),
        )
        settings = _settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.sqlite")
        )

        import pytest

        with pytest.raises(RuntimeError, match="query parser exploded"):
            agent_graph.run_agent_query(
                "How much did I spend?", "user-1", "conv-1", settings
            )

        update_trace.assert_called_once()
        _, kwargs = update_trace.call_args
        assert kwargs["level"] == "ERROR"

    def test_tracing_being_unconfigured_does_not_change_the_result(
        self, mocker, tmp_path
    ):
        """With no Langfuse keys set, start_trace naturally returns None
        (see rag_api/tracing.py) - run_agent_query must behave identically
        to the untraced path."""
        mocker.patch(
            "rag_api.query_parser.parse_query", return_value=_make_parsed_query()
        )
        mocker.patch("rag_pipeline.search", return_value=[_make_result()])
        mocker.patch(
            "rag_api.openai_client.ask_openai", return_value=("An answer.", [])
        )
        mocker.patch(
            "rag_api.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=True, issues=""),
        )
        settings = _settings(
            agent_checkpoint_db_path=str(tmp_path / "checkpoints.sqlite")
        )

        result = agent_graph.run_agent_query(
            "How much did I spend?", "user-1", "conv-1", settings
        )

        assert result["answer"] == "An answer."

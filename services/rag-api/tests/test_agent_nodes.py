"""Unit tests for the groundedness self-critique loop (critique_node,
route_after_critique, and generate_node's feedback wiring). See
rag_api/agent/nodes.py and rag_api/openai_client.check_groundedness.
"""

from __future__ import annotations

from rag_pipeline.search import SearchResult

from rag_api.agent import nodes
from rag_api.agent.state import MAX_CRITIQUE_ATTEMPTS
from rag_api.openai_client import GroundednessResult


def _make_result(**overrides):
    defaults = dict(
        chunk_text="Some chunk of text.",
        chunk_metadata={"token_count": 42},
        filename="statement.pdf",
        similarity=0.87,
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


class TestCritiqueNode:
    def test_grounded_answer_is_a_no_op(self, mocker):
        mocker.patch(
            "rag_api.agent.nodes.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=True, issues=""),
        )
        state = {
            "question": "How much did I spend?",
            "answer": "You spent $50.",
            "results": [_make_result()],
        }

        result = nodes.critique_node(state, settings=object())

        # critique_feedback is explicitly cleared (not just absent) so a
        # stale critique_feedback from an earlier regeneration round can't
        # make route_after_critique loop back to generate again.
        assert result == {"critique_feedback": None, "grounded": True}

    def test_ungrounded_answer_returns_feedback_and_increments_attempt(self, mocker):
        mocker.patch(
            "rag_api.agent.nodes.openai_client.check_groundedness",
            return_value=GroundednessResult(
                grounded=False, issues="Claims a $50 figure not present in excerpts."
            ),
        )
        state = {
            "question": "How much did I spend?",
            "answer": "You spent $50.",
            "results": [_make_result()],
            "critique_attempt": 0,
        }

        result = nodes.critique_node(state, settings=object())

        assert result["critique_feedback"] == (
            "Claims a $50 figure not present in excerpts."
        )
        assert result["critique_attempt"] == 1
        assert result["grounded"] is False

    def test_ungrounded_answer_with_empty_issues_still_triggers_a_retry(self, mocker):
        """The judge can legally return {"grounded": false, "issues": ""}
        under the declared schema (issues has no minLength). Routing must
        not rely on critique_feedback's string truthiness for this."""
        mocker.patch(
            "rag_api.agent.nodes.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=False, issues=""),
        )
        state = {
            "question": "How much did I spend?",
            "answer": "You spent $50.",
            "results": [_make_result()],
            "critique_attempt": 0,
        }

        result = nodes.critique_node(state, settings=object())

        assert result["critique_feedback"] == ""
        assert result["critique_attempt"] == 1
        assert result["grounded"] is False
        assert nodes.route_after_critique({**state, **result}) == "generate"

    def test_ungrounded_answer_with_empty_issues_still_appends_caveat_when_exhausted(
        self, mocker
    ):
        mocker.patch(
            "rag_api.agent.nodes.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=False, issues=""),
        )
        state = {
            "question": "How much did I spend?",
            "answer": "You spent $50.",
            "results": [_make_result()],
            "critique_attempt": MAX_CRITIQUE_ATTEMPTS,
        }

        result = nodes.critique_node(state, settings=object())

        assert result["grounded"] is False
        assert "could not be fully verified" in result["answer"]
        assert nodes.route_after_critique({**state, **result}) == "end"

    def test_groundedness_check_failure_fails_open_as_a_no_op(self, mocker):
        mocker.patch(
            "rag_api.agent.nodes.openai_client.check_groundedness",
            side_effect=RuntimeError("openai timeout"),
        )
        state = {
            "question": "How much did I spend?",
            "answer": "You spent $50.",
            "results": [_make_result()],
        }

        result = nodes.critique_node(state, settings=object())

        assert result == {"critique_feedback": None, "grounded": True}

    def test_exhausted_retries_appends_a_soft_caveat_to_the_answer(self, mocker):
        mocker.patch(
            "rag_api.agent.nodes.openai_client.check_groundedness",
            return_value=GroundednessResult(grounded=False, issues="Still ungrounded."),
        )
        state = {
            "question": "How much did I spend?",
            "answer": "You spent $50.",
            "results": [_make_result()],
            "critique_attempt": MAX_CRITIQUE_ATTEMPTS,
        }

        result = nodes.critique_node(state, settings=object())

        assert "answer" in result
        assert result["answer"].startswith("You spent $50.")
        assert "could not be fully verified" in result["answer"]


class TestRouteAfterCritique:
    def test_no_verdict_routes_to_end(self):
        assert nodes.route_after_critique({}) == "end"

    def test_grounded_routes_to_end_even_with_stale_feedback_text(self):
        """grounded=True must win even if a stale critique_feedback string
        is still sitting in state from an earlier round."""
        state = {
            "grounded": True,
            "critique_feedback": "issue",
            "critique_attempt": 0,
        }
        assert nodes.route_after_critique(state) == "end"

    def test_ungrounded_under_attempt_cap_routes_to_generate(self):
        state = {"grounded": False, "critique_feedback": "issue", "critique_attempt": 0}
        assert nodes.route_after_critique(state) == "generate"

    def test_ungrounded_with_empty_feedback_still_routes_to_generate(self):
        """Regression: an ungrounded verdict with issues="" (a legal judge
        response) must still trigger the retry, not be treated as "no
        verdict" just because critique_feedback is an empty string."""
        state = {"grounded": False, "critique_feedback": "", "critique_attempt": 0}
        assert nodes.route_after_critique(state) == "generate"

    def test_ungrounded_still_within_budget_routes_to_generate(self):
        """critique_attempt here is the value already returned by
        critique_node after incrementing for the first ungrounded verdict -
        still within the MAX_CRITIQUE_ATTEMPTS budget, so one retry is
        granted."""
        state = {
            "grounded": False,
            "critique_feedback": "issue",
            "critique_attempt": MAX_CRITIQUE_ATTEMPTS,
        }
        assert nodes.route_after_critique(state) == "generate"

    def test_ungrounded_past_attempt_budget_routes_to_end(self):
        state = {
            "grounded": False,
            "critique_feedback": "issue",
            "critique_attempt": MAX_CRITIQUE_ATTEMPTS + 1,
        }
        assert nodes.route_after_critique(state) == "end"


class TestGenerateNodePassesCritiqueFeedback:
    def test_feedback_is_forwarded_to_ask_openai(self, mocker):
        ask_openai = mocker.patch(
            "rag_api.agent.nodes.openai_client.ask_openai",
            return_value=("A corrected answer.", []),
        )
        state = {
            "question": "How much did I spend?",
            "results": [_make_result()],
            "messages": [],
            "critique_feedback": "Claims a figure not present in excerpts.",
        }

        nodes.generate_node(state, settings=object())

        _, kwargs = ask_openai.call_args
        assert kwargs["critique_feedback"] == (
            "Claims a figure not present in excerpts."
        )

    def test_no_feedback_passes_none(self, mocker):
        ask_openai = mocker.patch(
            "rag_api.agent.nodes.openai_client.ask_openai",
            return_value=("An answer.", []),
        )
        state = {
            "question": "How much did I spend?",
            "results": [_make_result()],
            "messages": [],
        }

        nodes.generate_node(state, settings=object())

        _, kwargs = ask_openai.call_args
        assert kwargs["critique_feedback"] is None

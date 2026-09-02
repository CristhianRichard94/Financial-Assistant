"""Unit tests for the corrective retrieval-grading node (grade_node) and
its routing (route_after_retrieve, now gating on graded results). See
rag_api/agent/nodes.py and rag_api/agent/state.py.
"""

from __future__ import annotations

from rag_pipeline.search import SearchResult

from rag_api.agent import nodes
from rag_api.agent.state import MAX_RETRIEVE_ATTEMPTS, MIN_RELEVANCE_SIMILARITY


def _make_result(**overrides):
    defaults = dict(
        chunk_text="Some chunk of text.",
        chunk_metadata={"token_count": 42},
        filename="statement.pdf",
        similarity=0.87,
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


class TestGradeNode:
    def test_filters_out_low_similarity_results_keeps_high_similarity_ones(self):
        relevant = _make_result(similarity=0.9)
        irrelevant = _make_result(similarity=0.1)
        state = {"results": [relevant, irrelevant]}

        result = nodes.grade_node(state)

        assert result == {"results": [relevant]}

    def test_empty_results_returns_empty_without_crashing(self):
        state = {"results": []}

        result = nodes.grade_node(state)

        assert result == {"results": []}

    def test_missing_results_key_returns_empty_without_crashing(self):
        state = {}

        result = nodes.grade_node(state)

        assert result == {"results": []}

    def test_all_below_threshold_returns_empty_list(self):
        state = {
            "results": [
                _make_result(similarity=0.05),
                _make_result(similarity=0.29),
            ]
        }

        result = nodes.grade_node(state)

        assert result == {"results": []}

    def test_result_exactly_at_threshold_is_kept(self):
        """MIN_RELEVANCE_SIMILARITY itself is inclusive (>=), so it isn't
        arbitrarily discarded right at the boundary."""
        state = {"results": [_make_result(similarity=MIN_RELEVANCE_SIMILARITY)]}

        result = nodes.grade_node(state)

        assert result == {"results": [state["results"][0]]}


class TestRouteAfterRetrieveAfterGrading:
    """route_after_retrieve now runs against graded/filtered results, not
    raw retrieval output - these mirror the retrieve-emptiness routing
    tests' style (attempts-remaining -> refine, exhausted -> generate
    anyway so generate_node can say "not found")."""

    def test_relevant_results_route_to_generate(self):
        state = {"results": [_make_result(similarity=0.9)], "attempt": 1}

        assert nodes.route_after_retrieve(state) == "generate"

    def test_no_relevant_results_with_attempts_remaining_routes_to_refine(self):
        state = {"results": [], "attempt": 0}

        assert nodes.route_after_retrieve(state) == "refine"

        assert MAX_RETRIEVE_ATTEMPTS > 0  # sanity: budget exists to route into

    def test_no_relevant_results_with_attempts_exhausted_routes_to_generate(self):
        state = {"results": [], "attempt": MAX_RETRIEVE_ATTEMPTS}

        assert nodes.route_after_retrieve(state) == "generate"

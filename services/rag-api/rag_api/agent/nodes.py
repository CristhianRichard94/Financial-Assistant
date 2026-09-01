"""Node functions for the agentic query graph."""

from __future__ import annotations

import logging

import rag_pipeline
from rag_pipeline.config import DEFAULT_MATCH_COUNT

from rag_api import openai_client, query_parser
from rag_api.agent.state import (
    MAX_CRITIQUE_ATTEMPTS,
    MAX_RETRIEVE_ATTEMPTS,
    MIN_RELEVANCE_SIMILARITY,
    AgentState,
)
from rag_api.config import RagApiSettings

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_ANSWER = "I can only answer questions about your uploaded financial documents."

GROUNDEDNESS_CAVEAT = (
    "\n\nNote: this answer could not be fully verified against your documents."
)


def parse_node(state: AgentState, settings: RagApiSettings) -> dict:
    parsed = query_parser.parse_query(state["question"], settings)
    return {
        "rewritten_query": parsed.rewritten_query,
        "intent": parsed.intent,
        "date_from": parsed.date_from,
        "date_to": parsed.date_to,
        "document_type": parsed.document_type,
    }


def out_of_scope_node(state: AgentState) -> dict:
    return {"answer": OUT_OF_SCOPE_ANSWER, "sources": []}


def retrieve_node(state: AgentState, settings: RagApiSettings) -> dict:
    results = rag_pipeline.search(
        state["rewritten_query"],
        state["user_id"],
        k=DEFAULT_MATCH_COUNT,
        date_from=state.get("date_from"),
        date_to=state.get("date_to"),
        document_type=state.get("document_type"),
    )
    return {"results": results, "attempt": state.get("attempt", 0) + 1}


def grade_node(state: AgentState) -> dict:
    """Corrective retrieval grading: filter `results` down to chunks whose
    similarity score (already computed by rag_pipeline's hybrid+RRF search,
    see SearchResult.similarity) clears MIN_RELEVANCE_SIMILARITY.

    Deliberately a pure threshold check, not another OpenAI call - grading
    every retrieval with an LLM would double request latency/cost on every
    query, whereas this is free and deterministic. route_after_retrieve
    then decides generate vs refine based on this filtered list, so a
    retrieval that returned only noise (technically non-empty, but nothing
    above the relevance bar) is treated the same as an empty retrieval.
    """
    results = state.get("results") or []
    return {
        "results": [r for r in results if r.similarity >= MIN_RELEVANCE_SIMILARITY]
    }


def refine_node(state: AgentState) -> dict:
    logger.info(
        "Empty retrieval on attempt %s, dropping filters and retrying",
        state.get("attempt", 0),
    )
    return {"date_from": None, "date_to": None, "document_type": None}


def generate_node(state: AgentState, settings: RagApiSettings) -> dict:
    history = state.get("messages", [])
    critique_feedback = state.get("critique_feedback")
    answer, sources = openai_client.ask_openai(
        state["question"],
        state.get("results", []),
        settings,
        history=history,
        critique_feedback=critique_feedback,
    )
    updated_messages = [
        *history,
        {"role": "user", "content": state["question"]},
        {"role": "assistant", "content": answer},
    ]
    return {"answer": answer, "sources": sources, "messages": updated_messages}


def critique_node(state: AgentState, settings: RagApiSettings) -> dict:
    """Check whether generate_node's `answer` is grounded in the retrieved
    `results` and, if not, either request one regeneration (with feedback)
    or - once MAX_CRITIQUE_ATTEMPTS is exhausted - append a soft caveat and
    let the answer through as-is (see route_after_critique).

    Fails open on any error from check_groundedness itself: treated the
    same as "grounded", so a transient judge failure never blocks the user
    from receiving their already-generated answer. `check_groundedness`
    already fails open internally (see openai_client.py), but this
    defends against it raising anyway (e.g. an unexpected error not
    covered by its own try/except).
    """
    try:
        result = openai_client.check_groundedness(
            state["question"], state["answer"], state.get("results", []), settings
        )
    except Exception:
        logger.exception(
            "critique_node's groundedness check failed unexpectedly; "
            "failing open (treating answer as grounded)."
        )
        return {"critique_feedback": None, "grounded": True}

    if result.grounded:
        # Explicitly clear critique_feedback (rather than an empty {}):
        # on a regenerated answer that's now grounded, a prior round's
        # critique_feedback is still sitting in state, and route_after_
        # critique routes on its presence - leaving it set would make the
        # graph loop back to generate_node again despite this answer being
        # fine.
        return {"critique_feedback": None, "grounded": True}

    # `new_attempt` counts ungrounded verdicts seen so far, including this
    # one. While it's still within the allowed budget (<= MAX_CRITIQUE_
    # ATTEMPTS), route_after_critique sends the graph back to generate_node
    # for one more try. Once a verdict pushes it past the budget, this is
    # the last chance exhausted: append a non-alarming caveat instead of
    # looping again, so the user still gets an answer.
    new_attempt = state.get("critique_attempt", 0) + 1
    if new_attempt > MAX_CRITIQUE_ATTEMPTS:
        return {
            "critique_feedback": result.issues,
            "critique_attempt": new_attempt,
            "answer": state["answer"] + GROUNDEDNESS_CAVEAT,
            "grounded": False,
        }

    return {
        "critique_feedback": result.issues,
        "critique_attempt": new_attempt,
        "grounded": False,
    }


def route_after_parse(state: AgentState) -> str:
    return "out_of_scope" if state["intent"] == "out_of_scope" else "retrieve"


def route_after_retrieve(state: AgentState) -> str:
    """Runs after grade_node, so `results` here is already filtered down to
    chunks that cleared MIN_RELEVANCE_SIMILARITY - an empty list means
    either nothing was retrieved or nothing retrieved was relevant, and
    both are treated the same way: retry via refine while attempts remain,
    otherwise give up and let generate_node say "not found"."""
    if state.get("results"):
        return "generate"
    if state.get("attempt", 0) < MAX_RETRIEVE_ATTEMPTS:
        return "refine"
    return "generate"  # give up broadening filters, let generate_node say "not found"


def route_after_critique(state: AgentState) -> str:
    """Mirrors critique_node's own "still within budget" check: `<=`, not
    `<`, because critique_attempt in state has already been incremented by
    critique_node by the time this routing function runs - see the
    `new_attempt` comment in critique_node above.

    Routes on the explicit `grounded` flag set by critique_node, not on
    critique_feedback's string truthiness: the judge can legally return
    `{"grounded": false, "issues": ""}` under the declared schema, and an
    empty issues string is falsy - gating on it would silently skip the
    mandated retry/caveat for that (legal) response shape.
    """
    if state.get("grounded", True) is False and state.get("critique_attempt", 0) <= MAX_CRITIQUE_ATTEMPTS:
        return "generate"
    return "end"

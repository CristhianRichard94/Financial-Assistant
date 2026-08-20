"""Node functions for the agentic query graph."""

from __future__ import annotations

import logging

import rag_pipeline
from rag_pipeline.config import DEFAULT_MATCH_COUNT

from rag_api import openai_client, query_parser
from rag_api.agent.state import MAX_RETRIEVE_ATTEMPTS, AgentState
from rag_api.config import RagApiSettings

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_ANSWER = "I can only answer questions about your uploaded financial documents."


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


def refine_node(state: AgentState) -> dict:
    logger.info(
        "Empty retrieval on attempt %s, dropping filters and retrying",
        state.get("attempt", 0),
    )
    return {"date_from": None, "date_to": None, "document_type": None}


def generate_node(state: AgentState, settings: RagApiSettings) -> dict:
    answer, sources = openai_client.ask_openai(
        state["question"], state.get("results", []), settings
    )
    return {"answer": answer, "sources": sources}


def route_after_parse(state: AgentState) -> str:
    return "out_of_scope" if state["intent"] == "out_of_scope" else "retrieve"


def route_after_retrieve(state: AgentState) -> str:
    if state.get("results"):
        return "generate"
    if state.get("attempt", 0) < MAX_RETRIEVE_ATTEMPTS:
        return "refine"
    return "generate"  # give up broadening filters, let generate_node say "not found"

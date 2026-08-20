"""Shared state passed between graph nodes."""

from __future__ import annotations

from typing import Literal, TypedDict

from rag_pipeline.search import SearchResult

from rag_api.schemas import SourceOut

MAX_RETRIEVE_ATTEMPTS = 2


class AgentState(TypedDict, total=False):
    # input
    question: str
    user_id: str

    # set by parse_node
    rewritten_query: str
    intent: Literal["lookup", "aggregate", "compare", "out_of_scope"]
    date_from: str | None
    date_to: str | None
    document_type: str | None

    # set/updated by retrieve_node and refine_node
    results: list[SearchResult]
    attempt: int

    # set by generate_node (or the out-of-scope short-circuit)
    answer: str
    sources: list[SourceOut]

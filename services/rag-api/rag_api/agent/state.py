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

    # Multi-turn conversation history, persisted across calls to the graph
    # by the checkpointer keyed on thread_id (see graph.py). Each entry is
    # {"role": "user" | "assistant", "content": str}, accumulated by
    # generate_node after every answered turn. Kept as raw question/answer
    # pairs (not the retrieval-augmented prompt with excerpts) so history
    # replayed into later prompts stays small and reflects what the user
    # actually asked/was told, not the retrieved document text of past turns.
    messages: list[dict[str, str]]

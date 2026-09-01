"""Shared state passed between graph nodes."""

from __future__ import annotations

from typing import Literal, TypedDict

from rag_pipeline.search import SearchResult

from rag_api.schemas import SourceOut

MAX_RETRIEVE_ATTEMPTS = 2
MAX_CRITIQUE_ATTEMPTS = 1

# Minimum SearchResult.similarity (see rag_pipeline/search.py) for a
# retrieved chunk to be treated as relevant by grade_node. Chosen as a
# cheap, deterministic threshold rather than an LLM-graded check: grading
# every retrieval with another OpenAI call would double request latency/
# cost on every single query, whereas a similarity cutoff is free. 0.3 is
# a permissive floor - low enough not to discard genuinely relevant but
# imperfectly-worded matches, but high enough to catch the near-zero-
# similarity noise that hybrid search + RRF (see rag_pipeline/search.py)
# can still surface as technically non-empty results. rag_pipeline itself
# has no existing similarity-threshold constant to align with (only
# DEFAULT_MATCH_COUNT, a result-count cap, not a relevance cutoff).
MIN_RELEVANCE_SIMILARITY = 0.3


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

    # set/updated by critique_node after generate_node produces an answer
    critique_attempt: int
    critique_feedback: str | None
    # Explicit "was this verdict ungrounded" signal, always set by
    # critique_node (True on grounded/fail-open, False on ungrounded).
    # route_after_critique must gate on this, not on critique_feedback's
    # string truthiness - the judge can legally return issues="" alongside
    # grounded=false, and an empty string is falsy.
    grounded: bool

    # Multi-turn conversation history, persisted across calls to the graph
    # by the checkpointer keyed on thread_id (see graph.py). Each entry is
    # {"role": "user" | "assistant", "content": str}, accumulated by
    # generate_node after every answered turn. Kept as raw question/answer
    # pairs (not the retrieval-augmented prompt with excerpts) so history
    # replayed into later prompts stays small and reflects what the user
    # actually asked/was told, not the retrieved document text of past turns.
    messages: list[dict[str, str]]

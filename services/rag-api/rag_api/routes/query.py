"""Question-answering route: retrieve relevant chunks, then ask OpenAI.

Uses `rag_pipeline.search(...)` (module-qualified attribute access) so tests
can patch `rag_pipeline.search` directly.
"""

from __future__ import annotations

import logging
import uuid

import rag_pipeline
from fastapi import APIRouter, Depends, HTTPException, status
from rag_pipeline.config import DEFAULT_MATCH_COUNT

from rag_api import openai_client, query_parser
from rag_api.agent.graph import run_agent_query
from rag_api.auth import require_internal_api_key, require_user_id
from rag_api.config import load_rag_api_settings
from rag_api.rate_limiter import require_query_rate_limit
from rag_api.schemas import QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_internal_api_key)])

# Fixed canned response for questions the query-parsing layer classifies as
# out_of_scope (e.g. chitchat, general finance advice unrelated to the
# user's own documents). Short-circuits retrieval and the answer-synthesis
# OpenAI call entirely, since there's nothing to retrieve or answer.
OUT_OF_SCOPE_ANSWER = "I can only answer questions about your uploaded financial documents."


@router.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    user_id: str = Depends(require_user_id),
    _rate_limit: None = Depends(require_query_rate_limit),
) -> QueryResponse:
    settings = load_rag_api_settings()

    try:
        parsed = query_parser.parse_query(request.question, settings)

        if parsed.intent == "out_of_scope":
            return QueryResponse(answer=OUT_OF_SCOPE_ANSWER, sources=[])

        results = rag_pipeline.search(
            parsed.rewritten_query,
            user_id,
            k=DEFAULT_MATCH_COUNT,
            date_from=parsed.date_from,
            date_to=parsed.date_to,
            document_type=parsed.document_type,
        )
        # The original raw question (not the rewritten retrieval query) is
        # what the final answer should respond to - the rewrite is purely a
        # retrieval aid.
        answer, sources = openai_client.ask_openai(request.question, results, settings)
    except Exception:
        logger.exception("Failed to answer query")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to answer question.",
        ) from None

    return QueryResponse(answer=answer, sources=sources)


@router.post("/query/agent", response_model=QueryResponse)
def query_agent(
    request: QueryRequest,
    user_id: str = Depends(require_user_id),
    _rate_limit: None = Depends(require_query_rate_limit),
) -> QueryResponse:
    """Same contract as /query, but answered by the LangGraph agent (see
    rag_api/agent/graph.py): parse -> retrieve -> retry with broadened
    filters on an empty hit -> generate, instead of one straight-line pass.

    Also carries multi-turn conversation memory: pass back the
    `conversation_id` returned by a prior call to let the agent see that
    conversation's earlier turns (see AgentState.messages and
    rag_api/agent/graph.py's checkpointer). If `request.conversation_id` is
    omitted, a new one is generated and returned for the caller to reuse on
    the next turn.

    Shares its rate-limit bucket with /query (see
    `rag_api.rate_limiter.require_query_rate_limit`) rather than getting its
    own, separate limit.
    """
    settings = load_rag_api_settings()
    conversation_id = request.conversation_id or str(uuid.uuid4())

    try:
        final_state = run_agent_query(request.question, user_id, conversation_id, settings)
    except Exception:
        logger.exception("Failed to answer query via agent")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to answer question.",
        ) from None

    return QueryResponse(
        answer=final_state["answer"],
        sources=final_state.get("sources", []),
        conversation_id=conversation_id,
    )

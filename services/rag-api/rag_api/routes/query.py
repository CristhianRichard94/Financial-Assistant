"""Question-answering route: retrieve relevant chunks, then ask OpenAI.

Uses `rag_pipeline.search(...)` (module-qualified attribute access) so tests
can patch `rag_pipeline.search` directly.
"""

from __future__ import annotations

import logging

import rag_pipeline
from fastapi import APIRouter, Depends, HTTPException, status

from rag_api import openai_client
from rag_api.auth import require_internal_api_key, require_user_id
from rag_api.config import load_rag_api_settings
from rag_api.schemas import QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_internal_api_key)])


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, user_id: str = Depends(require_user_id)) -> QueryResponse:
    settings = load_rag_api_settings()

    try:
        results = rag_pipeline.search(request.question, user_id, k=5)
        answer, sources = openai_client.ask_openai(request.question, results, settings)
    except Exception:
        logger.exception("Failed to answer query")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to answer question.",
        ) from None

    return QueryResponse(answer=answer, sources=sources)

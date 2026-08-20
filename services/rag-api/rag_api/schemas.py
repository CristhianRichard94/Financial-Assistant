"""Pydantic request/response models for the RAG API.

`DocumentOut` fields are deliberately camelCase to match the frontend's
`Document` TypeScript interface (src/lib/store.ts in the Next.js app)
exactly, since these objects are returned as-is to the browser.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentStatusOut = Literal["pending", "processing", "processed", "error"]
DocumentTypeOut = Literal["pdf", "csv", "image"]


class DocumentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    type: DocumentTypeOut
    size: int
    status: DocumentStatusOut
    uploaded_at: str = Field(alias="uploadedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    # Only used by /query/agent (see rag_api/routes/query.py) to thread
    # multi-turn conversation memory through the LangGraph checkpointer.
    # Optional: omit it on the first turn of a conversation and the server
    # generates one (returned in QueryResponse.conversation_id); pass that
    # same value back on subsequent turns to keep seeing prior context.
    # Ignored entirely by the plain /query route, which stays single-turn.
    # max_length=100: UUIDs (the server-generated form) are 36 chars; this
    # leaves headroom for other reasonable client-supplied id formats while
    # still bounding it, consistent with `question`'s own max_length above.
    conversation_id: str | None = Field(default=None, max_length=100)


class SourceOut(BaseModel):
    filename: str
    similarity: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    # Echoes/assigns the conversation id for this exchange (see
    # QueryRequest.conversation_id): the client-supplied id, or a
    # server-generated one if none was supplied. Only populated by
    # /query/agent, which is the only route with conversation memory;
    # defaults to None (omitted) so the untouched, single-turn /query
    # route's response shape doesn't need to change.
    conversation_id: str | None = None

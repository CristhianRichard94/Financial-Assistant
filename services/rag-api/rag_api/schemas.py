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


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class SourceOut(BaseModel):
    filename: str
    similarity: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]

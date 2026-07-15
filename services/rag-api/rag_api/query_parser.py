"""Query-parsing layer: extract structured retrieval hints from a raw
question via an OpenAI call, run BEFORE retrieval.

This is an enhancement layer on top of retrieval, not a hard dependency -
see `parse_query`'s fail-open behavior below.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from rag_api.config import RagApiSettings
from rag_api.openai_client import get_client

logger = logging.getLogger(__name__)

MAX_TOKENS = 512

SYSTEM_PROMPT = (
    "You are a query understanding component for a financial-document RAG "
    "assistant. Users ask questions about their uploaded financial documents "
    "(bank/brokerage statements, invoices, contracts, tax forms, CSV "
    "transaction exports). Given the user's raw question and today's date, "
    "extract structured retrieval hints and produce a cleaner search query.\n\n"
    "Output strictly the JSON fields defined by the schema. Do not answer the "
    "question - you are not the assistant, you only prepare it for "
    "retrieval.\n\n"
    "Guidelines:\n"
    "- rewritten_query: Rewrite the question into a compact, keyword-rich "
    "search query optimized for both semantic embedding search and full-text "
    "keyword search. Expand abbreviations (e.g. \"acct\" -> \"account\"), "
    "spell out numbers found as words, resolve vague references using "
    "context if present, but do not invent facts. Preserve exact figures, "
    "account numbers, ticker symbols verbatim.\n"
    "- intent: one of \"lookup\" (asking for a specific fact/value), "
    "\"aggregate\" (sum/average/total/count across multiple documents or "
    "entries), \"compare\" (comparing two periods/entities), \"out_of_scope\" "
    "(not about the user's financial documents, e.g. chitchat or general "
    "finance advice unrelated to their data).\n"
    "- date_from / date_to: If the question references a time period (a "
    "month, quarter, year, \"last week\", \"since January\"), resolve it to "
    "concrete ISO 8601 dates (YYYY-MM-DD) using today's date as reference. "
    "Null if no time constraint is expressed.\n"
    "- document_type: one of \"pdf\", \"csv\", \"image\", or null if the "
    "question doesn't imply a specific source format (e.g. \"in my CSV "
    "export\" -> csv).\n"
    "- entities: list of notable literal identifiers mentioned - amounts, "
    "account numbers, ticker symbols, merchant/counterparty names. Empty "
    "list if none.\n\n"
    "Never fabricate dates, amounts, or identifiers not present in the "
    "question."
)

_INTENT_VALUES = ("lookup", "aggregate", "compare", "out_of_scope")
_DOCUMENT_TYPE_VALUES = ("pdf", "csv", "image")

_JSON_SCHEMA = {
    "name": "parsed_query",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "rewritten_query": {"type": "string"},
            "intent": {"type": "string", "enum": list(_INTENT_VALUES)},
            "date_from": {"type": ["string", "null"]},
            "date_to": {"type": ["string", "null"]},
            "document_type": {
                "type": ["string", "null"],
                "enum": [*_DOCUMENT_TYPE_VALUES, None],
            },
            "entities": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "rewritten_query",
            "intent",
            "date_from",
            "date_to",
            "document_type",
            "entities",
        ],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class ParsedQuery:
    rewritten_query: str
    intent: Literal["lookup", "aggregate", "compare", "out_of_scope"]
    date_from: str | None = None
    date_to: str | None = None
    document_type: Literal["pdf", "csv", "image"] | None = None
    entities: list[str] = field(default_factory=list)


def _default_parsed_query(question: str) -> ParsedQuery:
    """The fail-open default: pass the raw question straight through as the
    retrieval query with no filters applied.

    Query parsing is a retrieval-quality enhancement, not a hard dependency
    of `/query` - if the OpenAI call or its JSON response is malformed for
    any reason, retrieval should still proceed using the user's raw
    question rather than the whole endpoint failing.
    """
    return ParsedQuery(rewritten_query=question, intent="lookup")


def _build_user_prompt(question: str) -> str:
    return f"Today's date: {date.today().isoformat()}\n\nQuestion: {question}"


def parse_query(question: str, settings: RagApiSettings) -> ParsedQuery:
    """Extract structured retrieval hints from `question` via an OpenAI call.

    Fails open: on any API/parse error, logs and returns a default
    ParsedQuery that just passes `question` through unchanged (see
    `_default_parsed_query`), so retrieval still works if parsing fails.
    """
    try:
        client = get_client(settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_chat_model,
            max_completion_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(question)},
            ],
            response_format={"type": "json_schema", "json_schema": _JSON_SCHEMA},
        )

        content = response.choices[0].message.content
        payload = json.loads(content)

        intent = payload["intent"]
        if intent not in _INTENT_VALUES:
            raise ValueError(f"Unexpected intent value: {intent!r}")

        document_type = payload.get("document_type")
        if document_type is not None and document_type not in _DOCUMENT_TYPE_VALUES:
            raise ValueError(f"Unexpected document_type value: {document_type!r}")

        return ParsedQuery(
            rewritten_query=payload["rewritten_query"],
            intent=intent,
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            document_type=document_type,
            entities=list(payload.get("entities") or []),
        )
    except Exception:
        logger.exception("Failed to parse query; falling back to raw question")
        return _default_parsed_query(question)

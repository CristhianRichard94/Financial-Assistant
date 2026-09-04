"""Embedding generation via OpenAI's text-embedding-3-small.

OpenAI is the only embedding provider used here: text-embedding-3-small is
the model this pipeline is built around, and Anthropic does not currently
offer a public embeddings endpoint, so there is no equivalent model to fall
back to.
"""

from __future__ import annotations

import httpx
from openai import OpenAI

from rag_pipeline.config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

_client: OpenAI | None = None

# See rag_api/openai_client.py's get_client for why timeout/max_retries are
# set explicitly: openai-python already retries transient errors (timeouts,
# connection errors, 429, 5xx) with backoff+jitter, and never retries 4xx -
# but its default timeout (600s read) is far too long to fail fast enough
# for callers that need a bounded budget.
_REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=20.0)
_MAX_RETRIES = 2


def get_client(api_key: str) -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=api_key, timeout=_REQUEST_TIMEOUT, max_retries=_MAX_RETRIES)
    return _client


def embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    """Embed a batch of texts, returning one 1536-dim vector per input text.

    OpenAI's embeddings endpoint accepts a list of inputs in a single
    request, so batching here is a single API call rather than one per chunk.
    """
    if not texts:
        return []

    client = get_client(api_key)
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    # The API preserves input order in its response.
    embeddings = [item.embedding for item in response.data]

    for embedding in embeddings:
        if len(embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSIONS}-dimensional embeddings from "
                f"{EMBEDDING_MODEL}, got {len(embedding)}. Check EMBEDDING_MODEL "
                f"in config.py matches the pgvector column dimension."
            )
    return embeddings


def embed_text(text: str, api_key: str) -> list[float]:
    """Embed a single text (e.g. a search query)."""
    return embed_texts([text], api_key)[0]

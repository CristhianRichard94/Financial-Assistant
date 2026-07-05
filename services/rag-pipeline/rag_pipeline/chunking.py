"""Token-aware chunking using tiktoken.

Chunks are sized in tokens (not characters/words) so they line up with the
actual unit the embedding model bills and truncates on.
"""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from rag_pipeline.config import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS, TOKEN_ENCODING


@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    token_count: int


def _get_encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(TOKEN_ENCODING)


def chunk_text(
    text: str,
    chunk_size_tokens: int = CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Split text into overlapping chunks of roughly chunk_size_tokens tokens.

    Consecutive chunks overlap by chunk_overlap_tokens tokens so that context
    near a chunk boundary isn't lost entirely from either side.
    """
    if chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be positive")
    if chunk_overlap_tokens < 0 or chunk_overlap_tokens >= chunk_size_tokens:
        raise ValueError("chunk_overlap_tokens must be >= 0 and < chunk_size_tokens")

    text = text.strip()
    if not text:
        return []

    encoding = _get_encoding()
    tokens = encoding.encode(text)

    if len(tokens) <= chunk_size_tokens:
        return [Chunk(text=text, index=0, token_count=len(tokens))]

    stride = chunk_size_tokens - chunk_overlap_tokens
    chunks: list[Chunk] = []
    start = 0
    index = 0
    while start < len(tokens):
        end = min(start + chunk_size_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_str = encoding.decode(chunk_tokens).strip()
        if chunk_str:
            chunks.append(Chunk(text=chunk_str, index=index, token_count=len(chunk_tokens)))
            index += 1
        if end == len(tokens):
            break
        start += stride

    return chunks

"""Environment configuration for the RAG pipeline.

All required values are read from environment variables (see .env.example).
We load a local .env file if present, but real values must still be exported
one way or another before the pipeline can talk to Supabase or OpenAI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Embedding model + its fixed output dimensionality. Keep these two in sync:
# text-embedding-3-small always returns 1536-dimensional vectors, which must
# match the `vector(1536)` column type used in sql/003_create_document_chunks_table.sql.
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# tiktoken encoding used by text-embedding-3-small (and the GPT-4o / GPT-4
# family), used here purely for token counting during chunking.
TOKEN_ENCODING = "cl100k_base"

# Chunking defaults.
CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50

DEFAULT_MATCH_COUNT = 5


class MissingEnvironmentVariable(RuntimeError):
    """Raised when a required environment variable is not set."""


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_key: str
    openai_api_key: str


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingEnvironmentVariable(
            f"Required environment variable '{name}' is not set. "
            f"Copy services/rag-pipeline/.env.example to .env and fill it in, "
            f"or export it in your shell."
        )
    return value


def load_settings() -> Settings:
    """Load and validate all environment variables the pipeline needs.

    Raises MissingEnvironmentVariable with a human-readable message if any
    required variable is absent, instead of failing deep inside a client
    library with a raw traceback.
    """
    return Settings(
        supabase_url=_require_env("SUPABASE_URL"),
        supabase_service_key=_require_env("SUPABASE_SERVICE_KEY"),
        openai_api_key=_require_env("OPENAI_API_KEY"),
    )

"""Environment configuration for the RAG API service.

Reuses `rag_pipeline`'s own `Settings`/`load_settings()` for the Supabase and
OpenAI credentials (this service always builds them at request-handling
time via `rag_pipeline`), and adds the internal-auth and answer-synthesis
configuration on top of that.

Note: `OPENAI_API_KEY` is read independently here (via `_require_env`, same
env var name `rag_pipeline.config.load_settings()` reads) rather than by
importing `rag_pipeline`'s `Settings`, so this module has no import-time
dependency on `rag_pipeline` and stays a plain, self-contained settings
loader - `rag_pipeline.load_settings()` is still the source of truth for
Supabase/embeddings configuration, invoked separately wherever the pipeline
itself is called.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# The OpenAI chat model used to synthesize answers from retrieved chunks.
# This is a fixed constant, not env-configurable, so all deployments of this
# service behave consistently. Distinct from rag_pipeline's EMBEDDING_MODEL
# (text-embedding-3-small), which is a separate model used for a separate
# purpose (embeddings, not chat completions).
OPENAI_CHAT_MODEL = "gpt-5"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB, matches the frontend's own limit.

ALLOWED_EXTENSIONS = {".pdf", ".csv", ".jpg", ".jpeg", ".png"}


class MissingEnvironmentVariable(RuntimeError):
    """Raised when a required environment variable is not set."""


@dataclass(frozen=True)
class RagApiSettings:
    openai_api_key: str
    internal_api_key: str
    openai_chat_model: str = OPENAI_CHAT_MODEL
    max_upload_bytes: int = MAX_UPLOAD_BYTES
    allowed_extensions: frozenset[str] = frozenset(ALLOWED_EXTENSIONS)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingEnvironmentVariable(
            f"Required environment variable '{name}' is not set. "
            f"Copy services/rag-api/.env.example to .env and fill it in, "
            f"or export it in your shell."
        )
    return value


def load_rag_api_settings() -> RagApiSettings:
    """Load and validate the OpenAI-specific and internal-auth configuration.

    Raises MissingEnvironmentVariable with a human-readable message if
    OPENAI_API_KEY or INTERNAL_API_KEY is absent. Supabase credentials are
    validated separately by `rag_pipeline.config.load_settings()` wherever
    the pipeline is actually invoked (it re-reads the same OPENAI_API_KEY
    env var for embeddings).
    """
    return RagApiSettings(
        openai_api_key=_require_env("OPENAI_API_KEY"),
        internal_api_key=_require_env("INTERNAL_API_KEY"),
    )

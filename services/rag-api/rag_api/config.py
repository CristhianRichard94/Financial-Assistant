"""Environment configuration for the RAG API service.

Reuses `rag_pipeline`'s own `Settings`/`load_settings()` for the Supabase and
OpenAI credentials (this service always builds them at request-handling
time via `rag_pipeline`), and adds the Anthropic-specific configuration on
top of that.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# The Claude model used to synthesize answers from retrieved chunks. This is
# a fixed constant, not env-configurable, so all deployments of this service
# behave consistently.
ANTHROPIC_MODEL = "claude-opus-4-8"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB, matches the frontend's own limit.

ALLOWED_EXTENSIONS = {".pdf", ".csv", ".jpg", ".jpeg", ".png"}


class MissingEnvironmentVariable(RuntimeError):
    """Raised when a required environment variable is not set."""


@dataclass(frozen=True)
class RagApiSettings:
    anthropic_api_key: str
    internal_api_key: str
    anthropic_model: str = ANTHROPIC_MODEL
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
    """Load and validate the Anthropic-specific and internal-auth configuration.

    Raises MissingEnvironmentVariable with a human-readable message if
    ANTHROPIC_API_KEY or INTERNAL_API_KEY is absent. Supabase/OpenAI
    credentials are validated separately by
    `rag_pipeline.config.load_settings()` wherever the pipeline is actually
    invoked.
    """
    return RagApiSettings(
        anthropic_api_key=_require_env("ANTHROPIC_API_KEY"),
        internal_api_key=_require_env("INTERNAL_API_KEY"),
    )

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

# Default per-user request-rate limits enforced by rag_api.rate_limiter (see
# that module's docstring for the algorithm/window used). Kept as named
# module constants, mirroring MAX_UPLOAD_BYTES above, so the actual numbers
# live in one place instead of being scattered as magic numbers across route
# code. Overridable via the QUERY_RATE_LIMIT_PER_MINUTE/
# UPLOAD_RATE_LIMIT_PER_MINUTE env vars - see `load_rag_api_settings` below,
# which re-reads them per call (same reasoning as AGENT_CHECKPOINT_DB_PATH
# just below: deliberately not frozen at import time, so a deployment can be
# tuned without a code change, and tests can monkeypatch a different value
# per test).
# /query and /query/agent (routes/query.py) share QUERY_RATE_LIMIT_PER_MINUTE
# - both trigger at least one paid OpenAI call per request, and a client
# could otherwise dodge a per-route limit by alternating between the two.
# /upload (routes/documents.py) gets its own, lower
# UPLOAD_RATE_LIMIT_PER_MINUTE bucket, since parsing/embedding/storing a
# whole document is heavier than a single query.
QUERY_RATE_LIMIT_PER_MINUTE = 20
UPLOAD_RATE_LIMIT_PER_MINUTE = 5

# Global (not per-user - /readyz is unauthenticated, see
# rag_api.rate_limiter's docstring) rate limit for /readyz, expressed as a
# request count within a 1-second trailing window. Deliberately generous
# relative to the ALB's own health-check cadence (every ~30s per target per
# infra/rag_api_stack.py) so normal health checks - including from multiple
# tasks/AZs polling concurrently - are never throttled, while still capping
# the rate an abusive caller can force real Supabase round-trips at (see
# health.py's `_check_supabase`). Overridable via READYZ_RATE_LIMIT_PER_SECOND
# for the same reasons as QUERY_RATE_LIMIT_PER_MINUTE/
# UPLOAD_RATE_LIMIT_PER_MINUTE above.
READYZ_RATE_LIMIT_PER_SECOND = 5

# Timeout (seconds) applied to the Supabase probe call in /readyz
# (health.py's `_check_supabase`). Without a bound, a Supabase instance that
# is slow rather than erroring outright would leave `/readyz` hanging for
# however long the underlying HTTP client's default timeout is, which could
# be well beyond the ALB's own health-check timeout - keeping this short
# means a slow-but-not-dead Supabase gets treated as not-ready quickly
# instead of blocking the request/thread indefinitely.
READYZ_SUPABASE_TIMEOUT_SECONDS = 3.0

# Default path for the agent's LangGraph checkpointer (see
# rag_api/agent/graph.py) to persist conversation state. SQLite-file-backed
# rather than in-memory so conversation history survives across requests
# within a single running process (in-memory would be lost the instant the
# request-handling coroutine returns). Overridable via the
# AGENT_CHECKPOINT_DB_PATH env var - see `load_rag_api_settings` below,
# which re-reads the env var per call (unlike OPENAI_CHAT_MODEL above, this
# one is deliberately re-read rather than frozen at import time, so tests
# can point each test run at its own isolated file via monkeypatch).
#
# This is only ever actually used when AGENT_CHECKPOINT_DB_URL is unset
# (local dev / pytest) - see agent_checkpoint_db_url below and
# rag_api/agent/graph.py for why real deployments use Postgres instead.
DEFAULT_AGENT_CHECKPOINT_DB_PATH = "agent_checkpoints.sqlite"


# `MissingEnvironmentVariable` and `_require_env` below intentionally
# duplicate the (near-identical) definitions in
# rag_pipeline/config.py rather than being imported from there - see this
# module's top-level docstring: this file is kept free of an import-time
# dependency on rag_pipeline on purpose, so this small duplication is
# accepted rather than refactored away.
class MissingEnvironmentVariable(RuntimeError):
    """Raised when a required environment variable is not set."""


@dataclass(frozen=True)
class RagApiSettings:
    openai_api_key: str
    internal_api_key: str
    openai_chat_model: str = OPENAI_CHAT_MODEL
    max_upload_bytes: int = MAX_UPLOAD_BYTES
    allowed_extensions: frozenset[str] = frozenset(ALLOWED_EXTENSIONS)
    agent_checkpoint_db_path: str = DEFAULT_AGENT_CHECKPOINT_DB_PATH
    # Postgres connection string for the agent's checkpointer (see
    # rag_api/agent/graph.py). Optional and unset by default (hence
    # os.environ.get, not _require_env below) so local dev and pytest keep
    # working with zero external dependencies via the SQLite fallback above.
    # When set in real deployments, this is a Secrets-Manager-sourced value
    # (see infra/rag_api_stack.py) - never log this value or include it in
    # an exception message, it embeds a DB credential.
    agent_checkpoint_db_url: str | None = None
    query_rate_limit_per_minute: int = QUERY_RATE_LIMIT_PER_MINUTE
    upload_rate_limit_per_minute: int = UPLOAD_RATE_LIMIT_PER_MINUTE
    readyz_rate_limit_per_second: int = READYZ_RATE_LIMIT_PER_SECOND


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingEnvironmentVariable(
            f"Required environment variable '{name}' is not set. "
            f"Copy services/rag-api/.env.example to .env and fill it in, "
            f"or export it in your shell."
        )
    return value


def _int_env(name: str, default: int) -> int:
    """Read `name` from the environment as an int, falling back to `default`
    if unset (or set to an empty string). Unlike `_require_env`, this is for
    optional settings - but if the variable *is* set, it must actually be a
    valid integer: raises MissingEnvironmentVariable (reusing the same
    "fail loud rather than silently misbehave" approach as `_require_env`)
    on a malformed value, instead of silently falling back to `default` or
    letting a confusing error surface later wherever the value gets used.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise MissingEnvironmentVariable(
            f"Environment variable '{name}' must be an integer if set (got {raw!r})."
        ) from None


def load_rag_api_settings() -> RagApiSettings:
    """Load and validate the OpenAI-specific and internal-auth configuration.

    Raises MissingEnvironmentVariable with a human-readable message if
    OPENAI_API_KEY or INTERNAL_API_KEY is absent, or if
    QUERY_RATE_LIMIT_PER_MINUTE/UPLOAD_RATE_LIMIT_PER_MINUTE is set but not a
    valid integer. Supabase credentials are validated separately by
    `rag_pipeline.config.load_settings()` wherever the pipeline is actually
    invoked (it re-reads the same OPENAI_API_KEY env var for embeddings).
    """
    return RagApiSettings(
        openai_api_key=_require_env("OPENAI_API_KEY"),
        internal_api_key=_require_env("INTERNAL_API_KEY"),
        agent_checkpoint_db_path=os.environ.get(
            "AGENT_CHECKPOINT_DB_PATH", DEFAULT_AGENT_CHECKPOINT_DB_PATH
        ),
        agent_checkpoint_db_url=os.environ.get("AGENT_CHECKPOINT_DB_URL"),
        query_rate_limit_per_minute=_int_env(
            "QUERY_RATE_LIMIT_PER_MINUTE", QUERY_RATE_LIMIT_PER_MINUTE
        ),
        upload_rate_limit_per_minute=_int_env(
            "UPLOAD_RATE_LIMIT_PER_MINUTE", UPLOAD_RATE_LIMIT_PER_MINUTE
        ),
        readyz_rate_limit_per_second=_int_env(
            "READYZ_RATE_LIMIT_PER_SECOND", READYZ_RATE_LIMIT_PER_SECOND
        ),
    )

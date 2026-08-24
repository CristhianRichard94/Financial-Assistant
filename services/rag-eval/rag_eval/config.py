"""Environment configuration for the rag-eval suite.

Reuses `rag_pipeline.config.load_settings()` and
`rag_api.config.load_rag_api_settings()` for the credentials the real
production code paths need (Supabase, OpenAI, INTERNAL_API_KEY), and adds
the eval-specific configuration (which user's ingested corpus to query, and
which model DeepEval uses as its LLM judge) on top of that.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Default LLM judge model for all DeepEval metrics, overridable via
# DEEPEVAL_JUDGE_MODEL. gpt-5 is the only chat model already configured in
# this repo (see rag_api/config.py's OPENAI_CHAT_MODEL), so it's reused here
# as the default rather than introducing a new one.
DEFAULT_JUDGE_MODEL = "gpt-5"

# Placeholder owner used if EVAL_USER_ID isn't set, matching the convention
# used by services/rag-pipeline/scripts/test_ingest_and_query.py's
# TEST_USER_ID default. Must be a real row in auth.users with the golden
# corpus already ingested for it (see golden/README.md).
DEFAULT_EVAL_USER_ID = "00000000-0000-0000-0000-000000000001"


class MissingEnvironmentVariable(RuntimeError):
    """Raised when a required environment variable is not set."""


@dataclass(frozen=True)
class EvalConfig:
    supabase_url: str
    supabase_service_key: str
    openai_api_key: str
    eval_user_id: str
    judge_model: str


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingEnvironmentVariable(
            f"Required environment variable '{name}' is not set. "
            f"Copy services/rag-eval/.env.example to .env and fill it in, "
            f"or export it in your shell."
        )
    return value


def required_env_vars_present() -> bool:
    """True iff every env var this suite needs to run against real
    infrastructure is set, without raising.

    Used by evals/conftest.py to decide whether to skip the whole suite
    cleanly instead of letting individual tests fail deep inside a client
    library with an opaque error.
    """
    return all(
        os.environ.get(name)
        for name in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    )


def load_eval_config() -> EvalConfig:
    """Load and validate all environment variables the eval suite needs.

    Raises MissingEnvironmentVariable with a human-readable message if any
    required variable is absent.
    """
    return EvalConfig(
        supabase_url=_require_env("SUPABASE_URL"),
        supabase_service_key=_require_env("SUPABASE_SERVICE_KEY"),
        openai_api_key=_require_env("OPENAI_API_KEY"),
        eval_user_id=os.environ.get("EVAL_USER_ID", DEFAULT_EVAL_USER_ID),
        judge_model=os.environ.get("DEEPEVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
    )

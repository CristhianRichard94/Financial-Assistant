"""Tests for rag_api.config.load_rag_api_settings, in particular the
Langfuse env var wiring (LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY/
LANGFUSE_HOST) that no other test exercises - the existing tracing tests
construct RagApiSettings(...) directly, bypassing env parsing entirely.
"""

from __future__ import annotations

from rag_api.config import DEFAULT_LANGFUSE_HOST, load_rag_api_settings


def _set_required_env(monkeypatch) -> None:
    """Set the two env vars load_rag_api_settings requires unconditionally,
    so tests below can focus purely on the Langfuse-related fields."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")


def test_load_rag_api_settings_reads_langfuse_env_vars(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test-123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test-456")
    monkeypatch.setenv("LANGFUSE_HOST", "https://self-hosted.example.com")

    settings = load_rag_api_settings()

    assert settings.langfuse_public_key == "pk-test-123"
    assert settings.langfuse_secret_key == "sk-test-456"
    assert settings.langfuse_host == "https://self-hosted.example.com"


def test_load_rag_api_settings_falls_back_to_default_langfuse_host_when_unset(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test-123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test-456")
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)

    settings = load_rag_api_settings()

    assert settings.langfuse_host == DEFAULT_LANGFUSE_HOST


def test_load_rag_api_settings_leaves_langfuse_keys_unset_when_absent(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)

    settings = load_rag_api_settings()

    assert settings.langfuse_public_key is None
    assert settings.langfuse_secret_key is None
    assert settings.langfuse_host == DEFAULT_LANGFUSE_HOST

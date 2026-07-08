"""Tests for prompt construction in rag_api.openai_client."""

from __future__ import annotations

from rag_pipeline.search import SearchResult

from rag_api.openai_client import build_prompt


def _make_result(**overrides):
    defaults = dict(
        chunk_text="Some chunk of text.",
        chunk_metadata={"token_count": 42},
        filename="statement.pdf",
        similarity=0.87,
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


def test_build_prompt_escapes_quotes_in_filename():
    result = _make_result(filename='foo.pdf"><script>alert(1)</script>')

    prompt = build_prompt("What did I spend?", [result])

    # The filename must never be able to close the source="..." attribute
    # or open a new tag inside the <excerpt> element.
    assert '"><script>' not in prompt
    assert "<script>" not in prompt
    assert '"' not in prompt.split('source="', 1)[1].split('"', 1)[0]


def test_build_prompt_strips_angle_brackets_from_filename():
    result = _make_result(filename="report<b>bold</b>.pdf")

    prompt = build_prompt("What did I spend?", [result])

    assert "<b>" not in prompt
    assert "</b>" not in prompt
    assert "<" not in prompt.split('source="', 1)[1].split('"', 1)[0]
    assert ">" not in prompt.split('source="', 1)[1].split('"', 1)[0]


def test_build_prompt_keeps_normal_filename_intact():
    result = _make_result(filename="bank_statement_may2025.pdf")

    prompt = build_prompt("What did I spend?", [result])

    assert 'source="bank_statement_may2025.pdf"' in prompt

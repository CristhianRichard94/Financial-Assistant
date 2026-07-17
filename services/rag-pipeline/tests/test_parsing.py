"""Tests for rag_pipeline.parsing: parse_document dispatch and parse_image."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rag_pipeline.parsing import parse_document, parse_image


def _fake_openai_response(text: str):
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def test_parse_image_extracts_text_via_vision_api(mocker, fake_settings, tmp_path):
    image_path = tmp_path / "receipt.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes")

    mock_create = mocker.Mock(
        return_value=_fake_openai_response("Coffee: $5.00\nTotal: $5.00")
    )
    mocker.patch(
        "rag_pipeline.parsing._get_client",
        return_value=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
        ),
    )

    result = parse_image(image_path, fake_settings)

    assert result == "Coffee: $5.00\nTotal: $5.00"
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-5"
    content = call_kwargs["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_parse_image_strips_whitespace_only_response(mocker, fake_settings, tmp_path):
    image_path = tmp_path / "blank.jpg"
    image_path.write_bytes(b"fake-jpg-bytes")

    mocker.patch(
        "rag_pipeline.parsing._get_client",
        return_value=SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=mocker.Mock(return_value=_fake_openai_response("   "))
                )
            )
        ),
    )

    assert parse_image(image_path, fake_settings) == ""


def test_parse_image_raises_when_api_key_missing(fake_settings, tmp_path):
    from dataclasses import replace

    settings = replace(fake_settings, openai_api_key="")
    image_path = tmp_path / "receipt.jpg"
    image_path.write_bytes(b"fake-jpg-bytes")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        parse_image(image_path, settings)


@pytest.mark.parametrize("suffix", [".jpg", ".jpeg", ".png"])
def test_parse_document_dispatches_images_to_parse_image(
    mocker, fake_settings, tmp_path, suffix
):
    image_path = tmp_path / f"receipt{suffix}"
    image_path.write_bytes(b"fake-image-bytes")

    mock_parse_image = mocker.patch(
        "rag_pipeline.parsing.parse_image", return_value="extracted text"
    )

    result = parse_document(image_path, settings=fake_settings)

    assert result == "extracted text"
    mock_parse_image.assert_called_once_with(image_path, fake_settings)


def test_parse_document_loads_settings_when_none_provided_for_image(
    mocker, fake_settings, tmp_path
):
    image_path = tmp_path / "receipt.png"
    image_path.write_bytes(b"fake-image-bytes")

    mocker.patch("rag_pipeline.parsing.load_settings", return_value=fake_settings)
    mock_parse_image = mocker.patch(
        "rag_pipeline.parsing.parse_image", return_value="extracted text"
    )

    result = parse_document(image_path)

    assert result == "extracted text"
    mock_parse_image.assert_called_once_with(image_path, fake_settings)


def test_parse_document_still_works_for_pdf_and_csv_without_settings(tmp_path):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("description,amount\nCoffee,5.00\n")

    assert parse_document(csv_path) == "description: Coffee | amount: 5.00"


def test_parse_document_raises_for_unsupported_extension(tmp_path):
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("hello")

    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_document(txt_path)

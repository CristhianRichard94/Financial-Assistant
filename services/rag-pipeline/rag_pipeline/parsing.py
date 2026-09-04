"""Parsing of source documents (PDF, CSV, image) into raw text."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
from openai import OpenAI
from pypdf import PdfReader

from rag_pipeline.config import VISION_MODEL, Settings, load_settings
from rag_pipeline.csv_source import read_csv

_IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

VISION_PROMPT = (
    "This image is a financial document (e.g. a receipt, bank/credit card "
    "statement, invoice, or pay stub). Transcribe ALL readable text, numbers, "
    "dates, and tabular data exactly as it appears in the image, preserving "
    "row/column structure where present (e.g. one line item per row). Do NOT "
    "describe the image or summarize it - produce a faithful text "
    "transcription only. If no text is legible, return an empty response."
)

_client: OpenAI | None = None

# See rag_api/openai_client.py's get_client for why timeout/max_retries are
# set explicitly: openai-python already retries transient errors (timeouts,
# connection errors, 429, 5xx) with backoff+jitter, and never retries 4xx -
# but its default timeout (600s read) is far too long to fail fast enough
# for callers that need a bounded budget. Vision transcription responses
# can legitimately take longer than a plain chat completion, hence the
# slightly higher read timeout here.
_REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=30.0)
_MAX_RETRIES = 2


def _get_client(api_key: str) -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=api_key, timeout=_REQUEST_TIMEOUT, max_retries=_MAX_RETRIES)
    return _client


def parse_pdf(path: Path) -> str:
    """Extract all text from a PDF, page by page.

    Pages that fail to yield any text (e.g. scanned image pages with no
    embedded text layer) contribute an empty string rather than raising,
    since pypdf's extract_text() already treats that case as empty output.
    """
    reader = PdfReader(str(path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages_text).strip()


def parse_csv(path: Path) -> str:
    """Render a CSV file as plain text, one line per row.

    Each row is rendered as "col1: val1 | col2: val2 | ..." using the header
    row as field names, which keeps row context inside a single chunk instead
    of relying on the model to infer column meaning from position alone.
    """
    _, rows = read_csv(path)
    lines = []
    for row in rows:
        rendered = " | ".join(f"{key}: {value}" for key, value in row.items())
        lines.append(rendered)
    return "\n".join(lines).strip()


def parse_image(path: Path, settings: Settings) -> str:
    """Extract text from an image document via OpenAI's vision-capable chat
    completions API (multimodal input, base64-encoded image data URL).

    Used for receipts, statements, invoices, and other financial documents
    supplied as .jpg/.jpeg/.png instead of PDF/CSV. Returns whatever text the
    model transcribes, which may be an empty string if nothing legible was
    found - callers (see ingest.process_document) already treat empty parsed
    text as a "No extractable text found" error, so that check is not
    duplicated here.
    """
    if not settings.openai_api_key:
        raise ValueError(
            "Cannot parse image: OPENAI_API_KEY is not configured. "
            "Set OPENAI_API_KEY in the environment or .env file."
        )

    suffix = path.suffix.lower()
    mime_type = _IMAGE_MIME_TYPES.get(suffix)
    if mime_type is None:
        raise ValueError(f"Unsupported image type '{suffix}'")

    image_bytes = path.read_bytes()
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded_image}"

    client = _get_client(settings.openai_api_key)
    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )

    content = response.choices[0].message.content
    return (content or "").strip()


def parse_document(path: Path, settings: Settings | None = None) -> str:
    """Parse a document based on its file extension.

    Supports .pdf, .csv, .jpg/.jpeg/.png. Raises ValueError for anything else.
    `settings` is only required for image files (it carries the OpenAI API
    key used for vision transcription); if omitted, it is loaded via
    `load_settings()` on demand so callers that only ever parse PDFs/CSVs are
    unaffected.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".csv":
        return parse_csv(path)
    if suffix in _IMAGE_MIME_TYPES:
        settings = settings or load_settings()
        return parse_image(path, settings)
    raise ValueError(
        f"Unsupported file type '{suffix}'. Supported: .pdf, .csv, .jpg, .jpeg, .png"
    )

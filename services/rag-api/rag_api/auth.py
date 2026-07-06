"""Defense-in-depth shared-secret authentication for the RAG API.

This service is designed to sit behind network-level access controls (an
internal ALB reachable only from the frontend's security group - see
infra/rag_api_stack.py and DEPLOYMENT.md), but network configuration alone
is easy to misconfigure or drift over time. This module adds a second,
application-level layer that fails closed even if the network boundary is
ever accidentally opened up: every route except /healthz requires a valid
`X-Internal-Api-Key` header matching a pre-shared secret.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from rag_api.config import load_rag_api_settings


async def require_internal_api_key(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-Api-Key"),
) -> None:
    """FastAPI dependency: reject the request unless it carries the correct
    shared-secret header.

    Uses `hmac.compare_digest` (constant-time comparison) instead of `==` to
    avoid leaking timing information about how much of the expected key was
    matched.
    """
    settings = load_rag_api_settings()
    if not x_internal_api_key or not hmac.compare_digest(
        x_internal_api_key, settings.internal_api_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid internal API key.",
        )

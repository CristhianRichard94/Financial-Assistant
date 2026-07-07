"""Primary shared-secret authentication for the RAG API.

The ALB fronting this service is public (reachable through the CloudFront
distribution in front of it - see infra/rag_api_stack.py and
DEPLOYMENT.md), so there is no network-level access control backing this
up: this header check is the primary access control for the service, not
a defense-in-depth layer. Every route except /healthz requires a valid
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

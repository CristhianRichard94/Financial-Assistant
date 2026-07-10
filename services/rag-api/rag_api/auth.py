"""Primary shared-secret authentication for the RAG API, plus the per-user
identity that rides along with it.

The ALB fronting this service is public (reachable through the CloudFront
distribution in front of it - see infra/rag_api_stack.py and
DEPLOYMENT.md), so there is no network-level access control backing this
up: this header check is the primary access control for the service, not
a defense-in-depth layer. Every route except /healthz requires a valid
`X-Internal-Api-Key` header matching a pre-shared secret.

Trust model for `X-User-Id` (multi-tenancy): this service is never reachable
by a browser directly - there is no CORS configuration, and the shared
secret above is the only thing that can call it. The Next.js server is the
sole caller, and by the time it calls rag-api it has already verified the
caller's Supabase Auth session (Google OAuth) itself. So exactly like the
shared secret, rag-api trusts an identity asserted by a caller it has
already authenticated: every route also requires an `X-User-Id` header
carrying that verified session's Supabase `auth.users.id` (a UUID), which
rag-api threads through every `rag_pipeline` call to scope reads/writes to
that user. rag-api does not (and cannot, on its own) verify that the id in
this header actually corresponds to the caller's real session - that
verification is Next.js's responsibility (see pass 2). rag-api's job is
narrower: reject the request outright if the header is missing or is not
even a syntactically valid UUID, rather than silently accepting garbage or
treating the request as unscoped.
"""

from __future__ import annotations

import hmac
import uuid

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


async def require_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """FastAPI dependency: validate `X-User-Id` and return it for route
    handlers to inject via `Depends`.

    Requires the header to be present and a syntactically valid UUID (per
    `uuid.UUID(...)`); rejects with 401 otherwise, matching
    `require_internal_api_key`'s "fail loud" behavior rather than silently
    treating a missing/malformed id as an unscoped or anonymous request.

    Does not itself re-check the internal API key - `require_internal_api_key`
    is applied at the router level alongside this dependency on every route
    (see routers in rag_api/routes/), so both are always enforced together.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header.",
        )
    try:
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header must be a valid UUID.",
        ) from None
    return x_user_id

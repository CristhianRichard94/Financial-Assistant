"""ASGI middleware providing a cheap, pre-parsing defense against oversized
request bodies.

This is deliberately a plain ASGI middleware (not `BaseHTTPMiddleware`), so it
runs ahead of *any* routing/dependency/body-parsing machinery and can reject
a request based purely on its headers, without FastAPI/Starlette touching the
body at all.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class ContentLengthLimitMiddleware:
    """Reject any HTTP request whose declared `Content-Length` already
    exceeds `max_bytes`, before Starlette/FastAPI parse the body at all.

    This is only a *first* line of defense: a client can lie about (or
    entirely omit) `Content-Length` and still stream an arbitrarily large
    body. The actual, authoritative bound on upload size is enforced while
    the body is being read - see `rag_api.routes.documents._stream_multipart_file`,
    which bounds the "file" field (and the request body as a whole) as it's
    read off the network, regardless of what this header claims. This
    middleware exists purely so a client that's honest about its
    Content-Length gets rejected immediately, with zero bytes of the body
    ever read off the socket.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_bytes = int(content_length)
            except ValueError:
                declared_bytes = None
            if declared_bytes is not None and declared_bytes > self.max_bytes:
                max_mb = self.max_bytes / (1024 * 1024)
                response = JSONResponse(
                    {"detail": f"Request body exceeds the {max_mb:.0f}MB size limit"},
                    status_code=400,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

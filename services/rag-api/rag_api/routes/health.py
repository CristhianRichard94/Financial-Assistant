"""Liveness/readiness endpoint for the ALB health check.

Deliberately has no auth and checks no downstream dependencies (Supabase,
OpenAI) - it only needs to prove the process is up and serving requests.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

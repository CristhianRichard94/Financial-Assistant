"""Thin wrapper around the supabase-py client.

Uses the service-role key (SUPABASE_SERVICE_KEY) since this pipeline runs as
a trusted backend job, not a client-facing, RLS-constrained user session.
"""

from __future__ import annotations

from supabase import Client, create_client

_client: Client | None = None


def get_supabase_client(url: str, service_key: str) -> Client:
    global _client
    if _client is None:
        _client = create_client(url, service_key)
    return _client

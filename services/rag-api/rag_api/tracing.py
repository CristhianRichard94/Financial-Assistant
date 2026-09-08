"""Optional Langfuse tracing/observability for this service's LLM call sites
(rag_api/openai_client.py's ask_openai/check_groundedness, and the
LangGraph agent nodes in rag_api/agent/nodes.py, wired together by
rag_api/agent/graph.py).

Tracing is entirely optional and fails open, always: if
LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY (see RagApiSettings) are unset, or
the Langfuse SDK itself fails for any reason - client construction,
network unreachability, a timeout, a malformed response, anything - the
wrapped business logic must still run and return its normal result/
exception to the caller completely unchanged. Every public function here
therefore either returns None/no-ops on failure, mirroring the fail-open
pattern already used by `openai_client._default_groundedness_result`, and
never lets a Langfuse-side exception propagate out to its caller.

Langfuse's own client batches and flushes generations asynchronously on a
background thread by default (`Langfuse.__init__`'s `flush_at`/
`flush_interval`); nothing in this module calls `.flush()` on the request
path, so tracing adds no meaningful blocking latency to a request.

Only the langfuse_* fields on RagApiSettings are ever read here - never
openai_api_key, agent_checkpoint_db_url, or internal_api_key - so no
secret can reach a Langfuse trace or a log line through this module.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any

from langfuse import Langfuse

from rag_api.config import RagApiSettings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None
_client_key: tuple[str, str, str] | None = None


@dataclass(frozen=True)
class TraceContext:
    """A handle to an in-flight Langfuse trace.

    Threaded through nested calls (run_agent_query -> generate_node ->
    ask_openai, run_agent_query -> critique_node -> check_groundedness) so
    every LLM call made during one agent run is recorded as a generation
    nested under the same trace, rather than each call starting its own
    disconnected trace. Two separate calls to run_agent_query - even for
    the same conversation_id - each get their own TraceContext and thus
    their own trace (trace-per-request).
    """

    trace_id: str


def _get_langfuse_client(settings: RagApiSettings) -> Langfuse | None:
    """Returns a cached Langfuse client for `settings`, or None if tracing
    is unconfigured (either langfuse_public_key or langfuse_secret_key is
    missing) or the client failed to construct.

    Never raises. Cached per (public_key, secret_key, host) tuple, the same
    pattern rag_api.openai_client.get_client uses for the OpenAI client, so
    repeated calls within one process reuse the same client/background
    flush thread instead of opening a new one per request.
    """
    global _client, _client_key

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    key = (settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host)
    if _client is not None and _client_key == key:
        return _client

    try:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _client_key = key
        return _client
    except Exception:
        logger.exception("Failed to initialize Langfuse client; tracing disabled.")
        _client = None
        _client_key = None
        return None


def start_trace(
    settings: RagApiSettings,
    *,
    name: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TraceContext | None:
    """Starts a new top-level Langfuse trace for one logical unit of work
    (e.g. one run_agent_query call).

    Returns None if tracing is unconfigured or the SDK call fails - callers
    must treat a None TraceContext the same as "tracing is off" and
    otherwise proceed exactly as if this call had succeeded, never raise or
    block on it.
    """
    client = _get_langfuse_client(settings)
    if client is None:
        return None
    try:
        trace = client.trace(name=name, user_id=user_id, session_id=session_id, metadata=metadata)
        return TraceContext(trace_id=trace.id)
    except Exception:
        logger.exception(
            "Failed to start Langfuse trace %r; tracing disabled for this call.", name
        )
        return None


def update_trace(
    settings: RagApiSettings,
    trace_context: TraceContext | None,
    *,
    output: Any = None,
    level: str | None = None,
    status_message: str | None = None,
) -> None:
    """Updates a previously-started trace with its final output and/or
    error status. A no-op if `trace_context` is None (tracing was never
    started for this call, e.g. unconfigured) or the SDK call fails.
    """
    if trace_context is None:
        return
    client = _get_langfuse_client(settings)
    if client is None:
        return
    try:
        kwargs: dict[str, Any] = {"id": trace_context.trace_id}
        if output is not None:
            kwargs["output"] = output
        if level is not None:
            kwargs["level"] = level
        if status_message is not None:
            kwargs["status_message"] = status_message
        client.trace(**kwargs)
    except Exception:
        logger.exception("Failed to update Langfuse trace; ignoring (fail-open).")


def record_generation(
    settings: RagApiSettings,
    trace_context: TraceContext | None,
    *,
    name: str,
    model: str,
    input_messages: Any,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    output: Any = None,
    usage: dict[str, int] | None = None,
    level: str = "DEFAULT",
    status_message: str | None = None,
) -> None:
    """Records one completed (successful or failed) LLM call as a Langfuse
    generation observation.

    If `trace_context` is given, the generation is attached to that trace
    (`trace_id`), so it shows up nested alongside every other generation
    recorded for the same run. If `trace_context` is None - the plain
    /query route's direct ask_openai/check_groundedness calls, which don't
    go through the agent graph - Langfuse creates an implicit standalone
    trace for the generation instead, so those calls are still traced on
    their own (trace-per-call).

    A no-op if tracing is unconfigured. Fails open (logs and returns)
    if the SDK call itself raises for any reason - a Langfuse outage or
    SDK bug must never surface as an error to ask_openai/check_groundedness
    callers, nor prevent the already-computed OpenAI result from being
    returned/raised as normal.
    """
    client = _get_langfuse_client(settings)
    if client is None:
        return
    try:
        kwargs: dict[str, Any] = dict(
            name=name,
            model=model,
            input=input_messages,
            output=output,
            start_time=start_time,
            end_time=end_time,
            level=level,
        )
        if status_message is not None:
            kwargs["status_message"] = status_message
        if usage:
            kwargs["usage_details"] = usage
        if trace_context is not None:
            kwargs["trace_id"] = trace_context.trace_id
        client.generation(**kwargs)
    except Exception:
        logger.exception(
            "Failed to record Langfuse generation %r; ignoring (fail-open).", name
        )

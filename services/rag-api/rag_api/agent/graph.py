"""Graph wiring for the agentic query flow.

    parse ---out_of_scope---> END (canned answer)
      |
      +---retrieve---> [empty?]--refine--> retrieve (loop, capped)
                          |
                          +--has results / attempts exhausted--> generate --> END

Settings aren't part of AgentState - bound into each node via
functools.partial at build time, so state stays pure/serializable data.
"""

from __future__ import annotations

import sqlite3
import threading
from functools import partial
from typing import Union

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from psycopg_pool import ConnectionPool

from rag_api.agent import nodes
from rag_api.agent.state import AgentState
from rag_api.config import RagApiSettings

# Module-level cache of one checkpointer (and its underlying sqlite3
# connection, or psycopg ConnectionPool) per checkpoint DB key, so repeated
# calls to `run_agent_query` within the same process share the same
# connection/pool rather than reopening it every request - `build_agent_graph`
# is called fresh per request, but the checkpointer it's given must be a
# long-lived object for checkpoints written in one request to be visible
# to `.get`/`.put` calls made in a later one.
#
# Two backends are supported, chosen via `settings.agent_checkpoint_db_url`:
#
# 1. Postgres (`PostgresSaver`, when AGENT_CHECKPOINT_DB_URL is set) - the
#    real-deployment path. This service runs on ECS Fargate with no
#    persistent volume mounted (see infra/rag_api_stack.py): the container's
#    filesystem is ephemeral, so a file-based checkpointer's data is wiped on
#    every task restart, redeploy, or crash. That's true today even at
#    desired_count=1 - it's not just a future multi-task scaling concern,
#    conversation memory silently doesn't survive a deploy right now.
#    Postgres (in practice, Supabase - the same project this service already
#    talks to via rag_pipeline) is a separate, persistent, network-accessible
#    store, so it survives task restarts and would also make cross-task
#    sharing correct if desired_count is ever raised above 1. Note that
#    "concurrent processes talking to this same Postgres backend" is also
#    already a present-day condition, not just a future desired_count>1
#    concern: ECS rolling deployments run the old and new task concurrently
#    for a window even at desired_count=1, so two processes can race through
#    first-time setup (see `_run_postgres_setup` below) on every deploy.
#
# 2. SQLite (`SqliteSaver`, when AGENT_CHECKPOINT_DB_URL is unset) - the
#    local-dev/test fallback, kept specifically so `pytest` and local
#    development keep working with zero external services (see
#    tests/conftest.py, which points AGENT_CHECKPOINT_DB_PATH at a per-test
#    temp file). It is still strictly better than
#    `langgraph.checkpoint.memory.MemorySaver` for that local use case:
#    MemorySaver's state lives only in that one Python process's memory and
#    would be lost the instant the process restarts, whereas a local SQLite
#    file at least survives across requests handled by the same process. But
#    it shares the same ephemeral-filesystem problem as (1) is meant to fix,
#    so it must never be the checkpointer used in a real deployment.
#
# Two separate locks (rather than one shared lock across both backends) so
# that first-time setup of one backend can never stall requests going
# through the other - most relevant for a slow/unreachable Postgres cold
# start blocking the (already-cheap, local-only) sqlite path.
_sqlite_checkpointer_lock = threading.Lock()
_postgres_checkpointer_lock = threading.Lock()
_sqlite_checkpointers: dict[str, SqliteSaver] = {}
_postgres_checkpointers: dict[str, tuple[ConnectionPool, PostgresSaver]] = {}

# Arbitrary fixed key for the Postgres session-level advisory lock acquired
# in `_run_postgres_setup` below. Any two processes racing through first-time
# setup must agree on the same key to actually serialize against each other,
# so this value must never change once deployed to an environment that may
# have concurrent tasks running old code. It has no meaning beyond "the key
# this service's checkpointer setup uses" - picked arbitrarily.
_SETUP_ADVISORY_LOCK_KEY = 8_741_223_390_112


def _get_sqlite_checkpointer(db_path: str) -> SqliteSaver:
    with _sqlite_checkpointer_lock:
        checkpointer = _sqlite_checkpointers.get(db_path)
        if checkpointer is None:
            # check_same_thread=False: FastAPI's sync route handlers may run
            # this connection from different worker threads across requests;
            # SqliteSaver does its own internal locking around access.
            conn = sqlite3.connect(db_path, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
            _sqlite_checkpointers[db_path] = checkpointer
        return checkpointer


def _run_postgres_setup(pool: ConnectionPool, checkpointer: PostgresSaver) -> None:
    """Run `checkpointer.setup()` serialized behind a Postgres session-level
    advisory lock, so two processes racing through first-time setup against
    the same (possibly still-empty) database can't corrupt/duplicate each
    other's migration bookkeeping.

    This matters today, not just at higher desired_count: ECS rolling
    deployments run the old and new task concurrently for a window even at
    desired_count=1 (see the module docstring above), so this is a
    present-day race, not a hypothetical future one.

    `langgraph-checkpoint-postgres`'s `PostgresSaver.setup()` (3.1.2, the
    version pinned here) creates a `checkpoint_migrations` bookkeeping table
    with `CREATE TABLE IF NOT EXISTS` and then applies migrations one at a
    time with `autocommit=True` - no transaction wrapping and no locking of
    its own - so it is not safe to call concurrently without an external
    lock like this one.
    """
    with pool.connection() as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_SETUP_ADVISORY_LOCK_KEY,))
        try:
            checkpointer.setup()
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_SETUP_ADVISORY_LOCK_KEY,))


def _get_postgres_checkpointer(db_url: str) -> PostgresSaver:
    with _postgres_checkpointer_lock:
        cached = _postgres_checkpointers.get(db_url)
        if cached is None:
            # autocommit=True + prepare_threshold=0 are both required for
            # compatibility with Supabase's Supavisor connection pooler
            # (the expected target here, in Session pooler mode - see
            # DEPLOYMENT.md), which does not support server-side prepared
            # statements. Without prepare_threshold=0, psycopg's default
            # behavior of preparing a statement after it's been executed a
            # few times will eventually fail against the pooler.
            connection_kwargs = {"autocommit": True, "prepare_threshold": 0}
            # Small pool: this pool is only ever used by this one
            # checkpointer within this one process, not shared with any
            # other query path, so it doesn't need to be sized like a
            # general-purpose app connection pool.
            pool = ConnectionPool(
                conninfo=db_url, max_size=5, kwargs=connection_kwargs, open=True
            )
            try:
                checkpointer = PostgresSaver(pool)
                # Idempotent - creates the checkpointer's tables with
                # IF NOT EXISTS semantics, so it's safe (and necessary,
                # since there's no separate migration step for this
                # service) to call on every process start. Wrapped in an
                # advisory lock - see _run_postgres_setup - to stay safe
                # under concurrent callers (e.g. rolling deploys).
                _run_postgres_setup(pool, checkpointer)
            except Exception:
                # Without this, a failure partway through setup (pool
                # construction succeeded but .setup() raised, e.g. a
                # transient connectivity blip or migration error) would
                # leak this pool's live connections/worker threads: it
                # would never be cached (so never reused), and never
                # closed (so never released) - and the next call would
                # open and potentially leak another one on retry.
                pool.close()
                raise
            cached = (pool, checkpointer)
            _postgres_checkpointers[db_url] = cached
        return cached[1]


def _get_checkpointer(
    settings: RagApiSettings,
) -> Union[SqliteSaver, PostgresSaver]:
    if settings.agent_checkpoint_db_url:
        return _get_postgres_checkpointer(settings.agent_checkpoint_db_url)
    return _get_sqlite_checkpointer(settings.agent_checkpoint_db_path)


def build_agent_graph(settings: RagApiSettings):
    graph = StateGraph(AgentState)

    graph.add_node("parse", partial(nodes.parse_node, settings=settings))
    graph.add_node("out_of_scope", nodes.out_of_scope_node)
    graph.add_node("retrieve", partial(nodes.retrieve_node, settings=settings))
    graph.add_node("refine", nodes.refine_node)
    graph.add_node("generate", partial(nodes.generate_node, settings=settings))

    graph.set_entry_point("parse")

    graph.add_conditional_edges(
        "parse",
        nodes.route_after_parse,
        {"out_of_scope": "out_of_scope", "retrieve": "retrieve"},
    )
    graph.add_conditional_edges(
        "retrieve",
        nodes.route_after_retrieve,
        {"refine": "refine", "generate": "generate"},
    )
    graph.add_edge("refine", "retrieve")
    graph.add_edge("out_of_scope", END)
    graph.add_edge("generate", END)

    checkpointer = _get_checkpointer(settings)
    return graph.compile(checkpointer=checkpointer)


def run_agent_query(
    question: str, user_id: str, conversation_id: str, settings: RagApiSettings
) -> AgentState:
    """Run one turn of the agent within conversation `conversation_id`.

    The checkpointer's `thread_id` is `f"{user_id}:{conversation_id}"`, not
    `conversation_id` alone. `conversation_id` is client-suppliable (see
    QueryRequest.conversation_id in rag_api/schemas.py) and echoed back in
    the response, so it must never be trusted as a sufficient key on its
    own: without binding it to `user_id`, one authenticated user could
    supply another user's conversation_id (guessed, leaked via logs/
    network/shared browser state, etc.) and have that other user's full
    Q&A history - a cross-tenant data leak - loaded and replayed into their
    own session. Every other rag_pipeline call in this service scopes by
    user_id (see rag_api/routes/query.py, rag_api/routes/documents.py);
    this keeps the agent's checkpointer consistent with that.

    Prior turns checkpointed under the same composite thread_id (e.g.
    accumulated `messages` history, see AgentState) are loaded automatically
    before this turn runs, and the resulting state - including this turn's
    appended history - is checkpointed back under the same thread_id for
    the next call to read.
    """
    app = build_agent_graph(settings)
    thread_id = f"{user_id}:{conversation_id}"
    return app.invoke(
        {"question": question, "user_id": user_id, "attempt": 0},
        config={"configurable": {"thread_id": thread_id}},
    )

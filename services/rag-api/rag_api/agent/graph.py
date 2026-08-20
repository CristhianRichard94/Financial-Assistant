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

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from rag_api.agent import nodes
from rag_api.agent.state import AgentState
from rag_api.config import RagApiSettings

# Module-level cache of one SqliteSaver (and its underlying sqlite3
# connection) per checkpoint DB path, so repeated calls to
# `run_agent_query` within the same process share the same connection
# rather than reopening the file every request - `build_agent_graph`
# is called fresh per request, but the checkpointer it's given must be a
# long-lived object for checkpoints written in one request to be visible
# to `.get`/`.put` calls made in a later one.
#
# Tradeoff (multi-worker deployment caveat): this is a *file-based SQLite*
# checkpointer rather than `langgraph.checkpoint.memory.MemorySaver`
# specifically because MemorySaver's state lives only in that one Python
# process's memory - it would NOT survive across the multiple uvicorn/
# gunicorn worker processes (or multiple ECS/Fargate tasks, see infra/)
# this service typically runs behind, since each worker/task has its own
# memory and a given conversation's requests aren't guaranteed to land on
# the same worker. A local SQLite file at least survives across requests
# handled by the *same* worker process, and is a real improvement over no
# persistence at all, but it still does NOT solve cross-worker or
# cross-task sharing: two requests for the same conversation_id that land
# on different workers/tasks (or different Fargate task instances, which
# don't share a filesystem) will each see only their own worker's SQLite
# file and miss the other's history. A production multi-worker/multi-task
# deployment needs a shared, network-accessible checkpointer (e.g.
# Postgres/Supabase-backed, via `langgraph-checkpoint-postgres`) - that is
# explicitly out of scope for this change and left as a follow-up.
_checkpointer_lock = threading.Lock()
_checkpointers: dict[str, SqliteSaver] = {}


def _get_checkpointer(db_path: str) -> SqliteSaver:
    with _checkpointer_lock:
        checkpointer = _checkpointers.get(db_path)
        if checkpointer is None:
            # check_same_thread=False: FastAPI's sync route handlers may run
            # this connection from different worker threads across requests;
            # SqliteSaver does its own internal locking around access.
            conn = sqlite3.connect(db_path, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
            _checkpointers[db_path] = checkpointer
        return checkpointer


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

    checkpointer = _get_checkpointer(settings.agent_checkpoint_db_path)
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

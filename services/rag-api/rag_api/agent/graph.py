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

from functools import partial

from langgraph.graph import END, StateGraph

from rag_api.agent import nodes
from rag_api.agent.state import AgentState
from rag_api.config import RagApiSettings


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

    return graph.compile()


def run_agent_query(question: str, user_id: str, settings: RagApiSettings) -> AgentState:
    app = build_agent_graph(settings)
    return app.invoke({"question": question, "user_id": user_id, "attempt": 0})

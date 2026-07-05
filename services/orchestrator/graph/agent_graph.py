"""
LangGraph agent graph — wires all nodes into the AKEA execution flow.

Graph topology (planner removed):
    START → retriever → reasoner → decider
                                      │
                    ┌─────────────────┤ _route_after_decision()
                    │                 │
                 [error]          [action]
                    │                 │
               responder         executor
                    ↑                 │
                    └─────────────────┘
                    responder → memory_writer → END

HITL implementation:
    The executor node uses langgraph.types.interrupt() for CRITICAL actions.
    The graph is compiled with PostgresSaver so state is persisted across
    restarts and multiple replicas.

Compilation:
    build_graph(conn_pool) → CompiledStateGraph
    One instance per service process (created once in lifespan).
    conn_pool must be a psycopg_pool.ConnectionPool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .nodes.decider import decider_node
from .nodes.executor import executor_node
from .nodes.memory_writer import memory_writer_node
from .nodes.reasoner import reasoner_node
from .nodes.responder import responder_node
from .nodes.retriever import retriever_node
from .state import GraphState

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool


def _route_after_decision(state: GraphState) -> str:
    """
    Conditional edge from decider.
    - If decider failed (error set, selected_action is None) → skip executor,
      go straight to responder. The user gets an honest error message.
    - Otherwise → executor (which internally calls interrupt() for CRITICAL).
    """
    if state.get("error") and not state.get("selected_action"):
        return "responder"
    return "executor"


def build_graph(conn_pool: ConnectionPool) -> CompiledStateGraph:
    """
    Build and compile the AKEA LangGraph agent graph.

    Args:
        conn_pool: A psycopg_pool.ConnectionPool used to create PostgresSaver.
                   Must already be open when this function is called.

    Returns:
        A compiled CompiledStateGraph ready for invoke() / stream() calls.
        Stored in app.state.agent_graph at service startup.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    builder = StateGraph(GraphState)

    # ── Register nodes ────────────────────────────────────────────────────────
    # Planner removed — redundant LLM call with no consumer.
    builder.add_node("retriever", retriever_node)
    builder.add_node("reasoner", reasoner_node)
    builder.add_node("decider", decider_node)
    builder.add_node("executor", executor_node)
    builder.add_node("responder", responder_node)
    builder.add_node("memory_writer", memory_writer_node)

    # ── Linear edges ──────────────────────────────────────────────────────────
    builder.add_edge(START, "retriever")
    builder.add_edge("retriever", "reasoner")
    builder.add_edge("reasoner", "decider")

    # ── Conditional edge: decider → executor | responder (on hard error) ──────
    builder.add_conditional_edges(
        "decider",
        _route_after_decision,
        {"executor": "executor", "responder": "responder"},
    )

    builder.add_edge("executor", "responder")
    builder.add_edge("responder", "memory_writer")
    builder.add_edge("memory_writer", END)

    # ── Compile with Postgres checkpointer ────────────────────────────────────
    checkpointer = PostgresSaver(conn_pool)
    checkpointer.setup()  # Creates checkpoint tables if they don't exist

    return builder.compile(checkpointer=checkpointer)

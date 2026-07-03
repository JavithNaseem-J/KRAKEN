"""
LangGraph agent graph — wires all nodes into the AKEA execution flow.

Graph topology:
    START → planner → retriever → reasoner → decider
                                                │
                              ┌─────────────────┤ route_after_decision()
                              │                 │
                           [SAFE]           [CRITICAL]
                              │                 │
                           executor ←─── (interrupt resumes here)
                              │
                           responder → END

HITL implementation:
    The executor node uses langgraph.types.interrupt() for CRITICAL actions.
    The graph is compiled with MemorySaver so state is persisted across
    the two HTTP calls (initial /run + /approval-callback resume).

Compilation:
    build_graph() → compiled CompiledStateGraph
    One instance per service process (created once in lifespan).
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .state import GraphState
from .nodes.planner       import planner_node
from .nodes.retriever     import retriever_node
from .nodes.reasoner      import reasoner_node
from .nodes.decider       import decider_node
from .nodes.executor      import executor_node
from .nodes.responder     import responder_node
from .nodes.memory_writer import memory_writer_node



def _route_after_decision(state: GraphState) -> str:
    """
    Conditional edge from decider.
    Routes to 'executor' for both SAFE and CRITICAL actions.
    The executor node internally calls interrupt() for CRITICAL — the routing
    logic stays simple here.
    Routes to 'responder' on error so the user always gets a response.
    """
    if state.get("error") and not state.get("selected_action"):
        return "responder"
    return "executor"


def build_graph() -> object:
    """
    Build and compile the AKEA LangGraph agent graph.

    Returns:
        A compiled CompiledStateGraph ready for invoke() calls.
        Stored in app.state.agent_graph at service startup.
    """
    builder = StateGraph(GraphState)

    # ── Register nodes ────────────────────────────────────────────────────────
    builder.add_node("planner",       planner_node)
    builder.add_node("retriever",     retriever_node)
    builder.add_node("reasoner",      reasoner_node)
    builder.add_node("decider",       decider_node)
    builder.add_node("executor",      executor_node)
    builder.add_node("responder",     responder_node)
    builder.add_node("memory_writer", memory_writer_node)


    # ── Linear edges ──────────────────────────────────────────────────────────
    builder.add_edge(START,       "planner")
    builder.add_edge("planner",   "retriever")
    builder.add_edge("retriever", "reasoner")
    builder.add_edge("reasoner",  "decider")

    # ── Conditional edge: decider → executor OR responder (on hard error) ─────
    builder.add_conditional_edges(
        "decider",
        _route_after_decision,
        {"executor": "executor", "responder": "responder"},
    )

    builder.add_edge("executor",      "responder")
    builder.add_edge("responder",     "memory_writer")
    builder.add_edge("memory_writer", END)


    # ── Compile with MemorySaver for HITL interrupt/resume support ────────────
    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)

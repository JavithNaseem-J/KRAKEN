from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import MemorySaver
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
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


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


def _create_graph_builder() -> StateGraph:
    """Create and wire the StateGraph structure for the AKEA agent."""
    builder = StateGraph(GraphState)

    builder.add_node("retriever", retriever_node)
    builder.add_node("reasoner", reasoner_node)
    builder.add_node("decider", decider_node)
    builder.add_node("executor", executor_node)
    builder.add_node("responder", responder_node)
    builder.add_node("memory_writer", memory_writer_node)

    builder.add_edge(START, "retriever")
    builder.add_edge("retriever", "reasoner")
    builder.add_edge("reasoner", "decider")
    builder.add_conditional_edges(
        "decider",
        _route_after_decision,
        {"executor": "executor", "responder": "responder"},
    )
    builder.add_edge("executor", "responder")
    builder.add_edge("responder", "memory_writer")
    builder.add_edge("memory_writer", END)

    return builder


async def build_graph_async(saver: AsyncPostgresSaver | None = None) -> CompiledStateGraph:
    """
    Build and compile the AKEA LangGraph agent graph with AsyncPostgresSaver or MemorySaver fallback.
    """
    builder = _create_graph_builder()
    if saver:
        await saver.setup()
        return builder.compile(checkpointer=saver)

    return builder.compile(checkpointer=MemorySaver())

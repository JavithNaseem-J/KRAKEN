from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.state import GraphState

from .nodes import (
    decider_node,
    executor_node,
    memory_writer_node,
    reasoner_node,
    responder_node,
    retriever_node,
)
from .router import route_after_decision

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


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
        route_after_decision,
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

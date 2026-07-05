"""
LangGraph-specific state schema for the AKEA agent graph.

Why separate from shared/models/agent.py:
  - LangGraph requires Annotated reducers on list fields (e.g. messages uses
    operator.add so turns are appended, not overwritten on each graph step).
  - The shared AgentState is the external API contract (request/response shapes).
  - This GraphState is the internal graph execution contract.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, NotRequired, Required, TypedDict


class ChunkDict(TypedDict):
    source: str
    content: str
    relevance_score: float
    metadata: dict[str, Any]


class GraphState(TypedDict):
    # ── Required Input & Output ───────────────────────────────────────────────
    session_id: Required[str]
    user_message: Required[str]
    messages: Required[Annotated[list[dict[str, str]], operator.add]]
    final_answer: NotRequired[str]

    # ── Optional/Computed Metadata ────────────────────────────────────────────
    user_id: NotRequired[str]

    # ── Retriever output ──────────────────────────────────────────────────────
    retrieved_chunks: NotRequired[list[ChunkDict]]

    # ── Reasoner output ───────────────────────────────────────────────────────
    reasoning: NotRequired[str]

    # ── Decider output ────────────────────────────────────────────────────────
    selected_action: NotRequired[str | None]  # String to dynamically match registry actions
    action_payload: NotRequired[dict[str, Any] | None]
    risk_level: NotRequired[Literal["SAFE", "CRITICAL"] | None]
    evidence: NotRequired[str | None]

    # ── HITL ──────────────────────────────────────────────────────────────────
    approval_id: NotRequired[str | None]
    approval_status: NotRequired[Literal["approved", "rejected", "timeout"] | None]

    # ── Executor output ───────────────────────────────────────────────────────
    action_result: NotRequired[dict[str, Any] | None]

    # ── Responder output ──────────────────────────────────────────────────────
    action_explanation: NotRequired[str]

    # ── Error passthrough ─────────────────────────────────────────────────────
    error: NotRequired[str | None]

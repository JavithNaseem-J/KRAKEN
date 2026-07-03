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
from typing import Annotated, Any, TypedDict


class GraphState(TypedDict, total=False):
    # ── Input ─────────────────────────────────────────────────────────────────
    session_id:   str
    user_id:      str
    user_message: str

    # ── Conversation history (append-only via reducer) ────────────────────────
    messages: Annotated[list[dict[str, str]], operator.add]

    # ── Planner output ────────────────────────────────────────────────────────
    plan_steps:   list[str]
    current_step: int

    # ── Retriever output ──────────────────────────────────────────────────────
    retrieved_chunks: list[dict[str, Any]]

    # ── Reasoner output ───────────────────────────────────────────────────────
    reasoning: str

    # ── Decider output ────────────────────────────────────────────────────────
    selected_action: str | None   # action name from registry, or "respond_only"
    action_payload:  dict[str, Any] | None
    risk_level:      str | None   # "SAFE" | "CRITICAL"

    # ── HITL ──────────────────────────────────────────────────────────────────
    approval_id:     str | None
    approval_status: str | None   # "approved" | "rejected" | "timeout"

    # ── Executor output ───────────────────────────────────────────────────────
    action_result: dict[str, Any] | None

    # ── Responder output ──────────────────────────────────────────────────────
    final_answer:       str
    action_explanation: str

    # ── Error passthrough ─────────────────────────────────────────────────────
    error: str | None

"""
Agent-level data contracts.
AgentState is the single mutable object that flows through the LangGraph graph.
All other types are request/response shapes for the orchestrator's FastAPI layer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from pydantic import BaseModel, Field


# ── LangGraph State ───────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    """
    The single state object passed between every LangGraph node.
    Fields are progressively populated as the graph executes.
    total=False means all fields are optional at construction time.
    """
    # ── Input ─────────────────────────────────────────────────────────────────
    session_id: str
    user_id: str
    user_message: str

    # ── Conversation history (short-term memory) ──────────────────────────────
    messages: list[dict[str, str]]          # [{role, content}, ...]

    # ── Planner output ────────────────────────────────────────────────────────
    plan_steps: list[str]
    current_step: int

    # ── Retriever output ──────────────────────────────────────────────────────
    retrieved_chunks: list[dict[str, Any]]

    # ── Reasoner output ───────────────────────────────────────────────────────
    reasoning: str

    # ── Decider output ────────────────────────────────────────────────────────
    selected_action: str | None
    action_payload: dict[str, Any] | None
    risk_level: str | None                  # "SAFE" | "CRITICAL"

    # ── HITL ──────────────────────────────────────────────────────────────────
    approval_id: str | None
    approval_status: str | None             # "pending"|"approved"|"rejected"|"timeout"

    # ── Executor output ───────────────────────────────────────────────────────
    action_result: dict[str, Any] | None

    # ── Responder output ──────────────────────────────────────────────────────
    final_answer: str
    action_explanation: str

    # ── Error ─────────────────────────────────────────────────────────────────
    error: str | None


# ── FastAPI contracts ─────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    """Inbound payload from the API gateway to the orchestrator."""
    user_id: str = Field(..., min_length=1, max_length=64)
    session_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    """Outbound payload from the orchestrator back to the caller."""
    session_id: str
    answer: str
    reasoning: str
    action_taken: str | None = None
    action_result: Any | None = None
    sources: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

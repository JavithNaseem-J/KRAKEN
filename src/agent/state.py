from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, NotRequired, Required, TypedDict


class ChunkDict(TypedDict):
    source: str
    content: str
    relevance_score: float
    metadata: dict[str, Any]


class GraphState(TypedDict):
    session_id: Required[str]
    user_message: Required[str]
    messages: Required[Annotated[list[dict[str, str]], operator.add]]
    final_answer: NotRequired[str]
    user_id: NotRequired[str]
    operator_role: NotRequired[str]
    retrieved_chunks: NotRequired[list[ChunkDict]]
    reasoning: NotRequired[str]
    selected_action: NotRequired[str | None]
    selected_actions: NotRequired[list[dict[str, Any]] | None]
    action_payload: NotRequired[dict[str, Any] | None]
    risk_level: NotRequired[Literal["SAFE", "CRITICAL"] | None]
    evidence: NotRequired[str | None]
    approval_id: NotRequired[str | None]
    approval_status: NotRequired[Literal["approved", "rejected", "timeout"] | None]
    action_result: NotRequired[dict[str, Any] | None]
    action_explanation: NotRequired[str]
    error: NotRequired[str | None]

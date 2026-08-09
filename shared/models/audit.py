from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AuditLogRequest(BaseModel):
    session_id: str
    user_id: str
    action_type: str
    action_name: str
    risk_level: str
    hitl_required: bool
    status: str
    reasoning: str | None = None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    hitl_decision: str | None = None

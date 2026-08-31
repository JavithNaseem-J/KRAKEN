from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from src.utils.privacy import strip_reasoning_fields


class AuditLogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_id: str
    action_type: str
    action_name: str
    risk_level: str
    hitl_required: bool
    status: str
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    hitl_decision: str | None = None

    @field_validator("payload", "result", mode="before")
    @classmethod
    def remove_private_reasoning(cls, value: Any) -> Any:
        return strip_reasoning_fields(value)

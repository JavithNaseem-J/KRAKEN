from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.utils.privacy import strip_reasoning_fields


class ActionType(StrEnum):
    READ = "READ"
    WRITE = "WRITE"


class RiskLevel(StrEnum):
    SAFE = "SAFE"  # No HITL required
    CRITICAL = "CRITICAL"  # HITL always required


class ActionDefinition(BaseModel):
    """Static metadata for a registered action (lives in the action registry)."""

    name: str
    description: str
    action_type: ActionType
    risk_level: RiskLevel
    requires_hitl: bool
    parameter_schema: dict[str, Any] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    """Payload sent from the orchestrator executor node to the action service."""

    model_config = ConfigDict(extra="forbid")

    action_name: str
    payload: dict[str, Any]
    session_id: str
    user_id: str
    demo_session_id: str | None = None
    demo_actor_id: str | None = None

    @field_validator("payload", mode="before")
    @classmethod
    def remove_private_reasoning(cls, value: Any) -> Any:
        return strip_reasoning_fields(value)


class ActionResult(BaseModel):
    """Response from the action service back to the orchestrator."""

    action_name: str
    success: bool
    result: Any | None = None
    error: str | None = None

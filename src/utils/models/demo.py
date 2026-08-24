from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DemoPersona(StrEnum):
    END_USER = "end_user"
    TIER1_ANALYST = "tier1_analyst"
    INCIDENT_COMMANDER = "incident_commander"
    ADMIN = "admin"


class DemoSessionResponse(BaseModel):
    session_id: str
    csrf_token: str
    persona: DemoPersona
    actor_id: str
    expires_at: datetime
    query_limit: int = Field(ge=1)
    write_limit: int = Field(ge=1)
    demo_mode: bool = True


class PersonaTransitionRequest(BaseModel):
    persona: DemoPersona
    csrf_token: str = Field(min_length=16, max_length=128)


class CsrfProof(BaseModel):
    csrf_token: str = Field(min_length=16, max_length=128)


class DemoSessionResetResponse(DemoSessionResponse):
    replaced_session: bool = True


class PersonaTransitionResponse(BaseModel):
    persona: DemoPersona
    actor_id: str
    clearance_level: str
    can_approve: bool


class CacheMetadata(BaseModel):
    hit: bool = False
    scope: str = "shared"
    knowledge_version: str | None = None
    embedding_model: str | None = None


class CapabilityState(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class CapabilityStatus(BaseModel):
    state: CapabilityState
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: CapabilityState
    capabilities: dict[str, CapabilityStatus]

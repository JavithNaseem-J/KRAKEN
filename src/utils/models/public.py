from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class BuildInfo(BaseModel):
    service: str = Field(min_length=1)
    application_version: str = Field(min_length=1)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    build_time: datetime

    @field_validator("build_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("build_time must include a timezone")
        return value


class OperationalPersona(StrEnum):
    END_USER = "end_user"
    TIER1_ANALYST = "tier1_analyst"
    INCIDENT_COMMANDER = "incident_commander"
    ADMIN = "admin"


class PublicSessionResponse(BaseModel):
    session_id: str
    csrf_token: str
    persona: OperationalPersona
    actor_id: str
    expires_at: datetime
    query_limit: int = Field(ge=1)
    write_limit: int = Field(ge=1)
    dataset_generation: str
    synthetic_environment: bool = True


class PersonaTransitionRequest(BaseModel):
    persona: OperationalPersona
    csrf_token: str = Field(min_length=16, max_length=128)


class CsrfProof(BaseModel):
    csrf_token: str = Field(min_length=16, max_length=128)


class PublicSessionResetResponse(PublicSessionResponse):
    replaced_session: bool = True


class PersonaTransitionResponse(BaseModel):
    persona: OperationalPersona
    actor_id: str
    clearance_level: str
    can_approve: bool


class CacheMetadata(BaseModel):
    hit: bool = False
    scope: str = "shared"
    knowledge_version: str | None = None
    embedding_model: str | None = None
    dataset_generation: str | None = None


class CapabilityState(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class CapabilityStatus(BaseModel):
    state: CapabilityState
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: CapabilityState
    dataset_generation: str
    capabilities: dict[str, CapabilityStatus]

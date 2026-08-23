from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


# FastAPI contracts
class QueryRequest(BaseModel):
    """Inbound payload from the API gateway to the orchestrator."""

    user_id: str = Field("anonymous", min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_@\.-]+$")
    session_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\.-]+$")
    message: str = Field("", min_length=0, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = Field(
        default=None, description="Unique request trace ID for distributed tracing"
    )


class QueryResponse(BaseModel):
    """Outbound payload from the orchestrator back to the caller."""

    session_id: str
    answer: str
    reasoning: str
    action_taken: str | None = None
    action_result: Any | None = None
    sources: list[str] = Field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    execution_time_sec: float | None = None
    execution_ms: int | None = None
    chunk_scores: list[float] | None = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trace_id: str | None = Field(
        default=None, description="Unique request trace ID for distributed tracing"
    )

"""
Canonical ErrorResponse Pydantic model for structured microservice error responses.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Canonical error response envelope used across all AKEA microservices."""

    error: str = Field(..., description="Human-readable summary error message.")
    code: str = Field(default="INTERNAL_ERROR", description="Machine-readable error code category.")
    details: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Detailed context, validation errors, or exception traces."
    )
    trace_id: str | None = Field(
        default=None, description="Request trace ID for distributed debugging."
    )

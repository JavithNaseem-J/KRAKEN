"""
Memory-layer data contracts.
Defines models for episodic and session memory request/response shapes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EpisodeStoreRequest(BaseModel):
    """Payload to store an episodic memory entry."""

    session_id: str
    user_id: str
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EpisodeSearchRequest(BaseModel):
    """Payload to search episodic memory entries."""

    query: str = Field(..., min_length=1)
    user_id: str
    top_k: int = Field(default=3, ge=1, le=20)


class EpisodeChunk(BaseModel):
    """A single retrieved episodic memory record."""

    id: str
    session_id: str
    content: str
    similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EpisodeSearchResponse(BaseModel):
    """Response payload containing matching episodic memories."""

    query: str
    user_id: str
    results: list[EpisodeChunk] = Field(default_factory=list)

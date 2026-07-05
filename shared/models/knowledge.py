"""
Knowledge-layer data contracts.
Defines the three knowledge sources, chunk representation,
and the retrieval request/response shapes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeSource(StrEnum):
    FAQ = "faq"  # Policy / FAQ documents
    TICKETS = "tickets"  # Past ticket history
    SLA = "sla"  # SLA / escalation rules


class KnowledgeChunk(BaseModel):
    """A single retrieved chunk from any knowledge source."""

    content: str
    source: KnowledgeSource
    document_id: str
    chunk_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class RetrievalRequest(BaseModel):
    """Payload from the orchestrator retriever node to the knowledge service."""

    query: str = Field(..., min_length=1)
    sources: list[KnowledgeSource] = Field(default_factory=lambda: list(KnowledgeSource))
    top_k: int = Field(default=5, ge=1, le=20)
    session_id: str


class RetrievalResult(BaseModel):
    """Response from the knowledge service to the orchestrator."""

    chunks: list[KnowledgeChunk]
    query: str
    total_retrieved: int
    sources_queried: list[KnowledgeSource]

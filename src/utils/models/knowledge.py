from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeSource(StrEnum):
    FAQ = "faq"  # Policy / FAQ documents
    TICKETS = "tickets"  # Past ticket history
    SLA = "sla"  # SLA / escalation rules


class TicketDocument(BaseModel):
    """Schema for raw ticket JSON records loaded during ingestion."""

    ticket_id: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    status: str = Field(default="open")
    priority: str = Field(default="medium")
    category: str = Field(default="general")
    description: str = Field(..., min_length=1)
    created_at: str | None = None
    resolved_at: str | None = None


class FAQDocument(BaseModel):
    """Schema for raw FAQ markdown/JSON records loaded during ingestion."""

    doc_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    category: str = Field(default="policy")


class KnowledgeChunkPayload(BaseModel):
    """Payload schema for points upserted into Qdrant vector database."""

    content: str = Field(..., min_length=1)
    source: KnowledgeSource
    document_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    title: str = Field(default="")
    category: str = Field(default="general")
    allowed_roles: list[str] = Field(default_factory=lambda: ["public"])
    embedding_model: str
    collection_version: str
    dataset_generation: str
    scope: str = "shared"
    expires_at: float | None = None
    untrusted_evidence: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    """A single retrieved chunk from any knowledge source."""

    content: str
    source: KnowledgeSource
    document_id: str
    chunk_id: str
    allowed_roles: list[str] = Field(default_factory=lambda: ["public"])
    metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)


class RetrievalRequest(BaseModel):
    """Payload from the orchestrator retriever node to the knowledge service."""

    query: str = Field(..., min_length=1)
    sources: list[KnowledgeSource] = Field(default_factory=lambda: list(KnowledgeSource))
    top_k: int = Field(default=5, ge=1, le=20)
    session_id: str
    user_role: str = Field(default="public")


class RetrievalResult(BaseModel):
    """Response from the knowledge service to the orchestrator."""

    chunks: list[KnowledgeChunk]
    query: str
    total_retrieved: int
    sources_queried: list[KnowledgeSource]

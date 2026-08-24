from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from qdrant_client.models import Document

from src.utils.config import get_settings

_MUTATION_PATTERN = re.compile(
    r"\b(create|open|close|escalate|unlock|quarantine|block|write|approve|reject)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CacheContext:
    role: str
    scope: str
    embedding_model: str
    knowledge_version: str

    def as_payload(self) -> dict[str, str]:
        return {
            "role": self.role,
            "scope": self.scope,
            "embedding_model": self.embedding_model,
            "knowledge_version": self.knowledge_version,
        }


def cache_context(metadata: dict[str, Any]) -> CacheContext:
    settings = get_settings()
    session_id = str(metadata.get("demo_session_id") or "")
    private = bool(metadata.get("has_private_uploads"))
    return CacheContext(
        role=str(metadata.get("operator_role") or "end_user"),
        scope=session_id if private and session_id else "shared",
        embedding_model=(
            settings.qdrant_inference_model
            if settings.qdrant_url and settings.qdrant_cloud_inference_enabled
            else settings.embedding_model
        ),
        knowledge_version=settings.knowledge_collection_version,
    )


def is_cache_eligible(message: str, metadata: dict[str, Any]) -> bool:
    return (
        bool(message.strip())
        and not _MUTATION_PATTERN.search(message)
        and not metadata.get("hitl_request")
    )


async def cache_query(message: str) -> Any:
    settings = get_settings()
    if settings.qdrant_url and settings.qdrant_cloud_inference_enabled:
        return Document(text=message, model=settings.qdrant_inference_model)
    from src.utils.embedder import get_embedder

    return await asyncio.to_thread(get_embedder().embed_query, message)

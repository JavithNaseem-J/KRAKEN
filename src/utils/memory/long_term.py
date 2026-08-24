from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Document,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.utils.cache import create_async_qdrant_client
from src.utils.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

EPISODIC_MEMORY_COLLECTION = "kraken_episodic_memory"


class LongTermMemory:
    """
    Qdrant-backed episodic memory store.
    Embedding model loaded once at startup — same unified model as the knowledge service.
    """

    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
        embedding_model: str = "BAAI/bge-small-en",
        device: str = "cpu",
        collection_name: str = EPISODIC_MEMORY_COLLECTION,
    ) -> None:
        self._client = client or create_async_qdrant_client()
        self._cloud_inference = bool(
            settings.qdrant_url and settings.qdrant_cloud_inference_enabled
        )
        self._model_name = (
            settings.qdrant_inference_model if self._cloud_inference else embedding_model
        )
        self._embedder: Any | None = None
        if not self._cloud_inference:
            from src.utils.embedder import get_embedder

            self._embedder = get_embedder()
        log.info("long_term.init", model=self._model_name, collection=collection_name)
        self._collection_name = collection_name
        self._dim = (
            settings.qdrant_inference_dim
            if self._cloud_inference
            else settings.embedding_dim or 384
        )
        log.info("long_term.ready")

    async def init(self) -> None:
        """Ensure the episodic memory collection and payload indexes exist in Qdrant."""
        try:
            if not await self._client.collection_exists(self._collection_name):
                await self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(
                        size=self._dim,
                        distance=Distance.COSINE,
                    ),
                )
                log.info("long_term.collection_created", collection=self._collection_name)

            # Ensure keyword index on user_id for fast filtered retrieval
            await self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="user_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            log.info("long_term.payload_index_ready", field="user_id")
        except Exception as exc:
            log.warning("long_term.init_warning", error=str(exc))

    async def _embed_async(self, text: str) -> Any:
        """Return a cloud inference document or a locally generated vector."""
        if self._cloud_inference:
            return Document(text=text, model=self._model_name)
        if self._embedder is None:
            raise RuntimeError("Long-term memory embedder is unavailable.")
        return await asyncio.to_thread(self._embedder.embed_query, text)

    async def store(
        self,
        session_id: str,
        user_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store an episodic memory entry with its embedding in Qdrant.
        Returns the UUID of the inserted point.
        """
        memory_id = str(uuid.uuid4())
        embedding = await self._embed_async(content)
        now_iso = datetime.now(UTC).isoformat()

        payload = {
            "id": memory_id,
            "session_id": session_id,
            "user_id": user_id,
            "content": content,
            "metadata": metadata or {},
            "timestamp": now_iso,
        }

        try:
            await self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    PointStruct(
                        id=memory_id,
                        vector=embedding,
                        payload=payload,
                    )
                ],
            )
            log.info("long_term.stored", session_id=session_id, id=memory_id, user_id=user_id)
        except Exception as exc:
            log.error("long_term.store_failed", error=str(exc), session_id=session_id)
            raise

        return memory_id

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the top_k most similar past memories for this user.
        Results filtered by user_id and sorted by cosine similarity descending.
        """
        embedding = await self._embed_async(query)
        top_k = max(1, min(top_k, 20))

        user_filter = Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id),
                )
            ]
        )

        try:
            res = await self._client.query_points(
                collection_name=self._collection_name,
                query=embedding,
                query_filter=user_filter,
                limit=top_k,
            )
            hits = res.points
        except Exception as exc:
            log.warning("long_term.search_warning", error=str(exc), user_id=user_id)
            return []

        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                {
                    "id": str(hit.id),
                    "session_id": payload.get("session_id", ""),
                    "content": payload.get("content", ""),
                    "metadata": payload.get("metadata", {}),
                    "timestamp": payload.get("timestamp", datetime.now(UTC).isoformat()),
                    "similarity": float(hit.score or 0.0),
                }
            )

        log.info(
            "long_term.search",
            user_id=user_id,
            results=len(results),
        )
        return results

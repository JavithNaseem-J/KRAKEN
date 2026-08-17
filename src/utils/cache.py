from __future__ import annotations

import json
import time
import uuid
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.utils.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

SEMANTIC_CACHE_COLLECTION = "kraken_semantic_cache"
SIMILARITY_THRESHOLD = 0.92


def create_async_qdrant_client() -> AsyncQdrantClient:
    """Factory returning a configured AsyncQdrantClient (remote Cloud or in-memory fallback)."""
    if settings.qdrant_url:
        log.info("qdrant.remote_client", url=settings.qdrant_url)
        return AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    log.info("qdrant.in_memory_client")
    return AsyncQdrantClient(location=":memory:")


class SemanticCache:
    """
    Qdrant-backed semantic response cache.

    Stores query vector embeddings and corresponding LLM responses.
    If an incoming query vector has Cosine similarity >= 0.92 and age <= ttl, returns cached response.

    Usage:
        cache = SemanticCache()
        await cache.init()          # called once during lifespan()
        result = await cache.get(vector)
        await cache.put(vector, query_text, response)
        await cache.invalidate()

    The constructor performs NO network I/O — collection setup is deferred to
    ``init()`` so it can be awaited inside an async lifespan context without
    blocking the event loop.
    """

    def __init__(
        self, client: AsyncQdrantClient | None = None, ttl_seconds: float = 3600.0
    ) -> None:
        self._client = client or create_async_qdrant_client()
        self._ttl_seconds = ttl_seconds

    async def init(self) -> None:
        """Ensure the cache collection exists. Must be awaited during service startup."""
        try:
            if not await self._client.collection_exists(SEMANTIC_CACHE_COLLECTION):
                await self._client.create_collection(
                    collection_name=SEMANTIC_CACHE_COLLECTION,
                    vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
                )
                log.info("semantic_cache.collection_created", collection=SEMANTIC_CACHE_COLLECTION, size=settings.embedding_dim)
            else:
                info = await self._client.get_collection(collection_name=SEMANTIC_CACHE_COLLECTION)
                vectors = info.config.params.vectors
                existing_size = getattr(vectors, "size", None)
                if isinstance(vectors, dict):
                    existing_size = vectors.get("size")
                if existing_size and existing_size != settings.embedding_dim:
                    log.error(
                        "semantic_cache.dimension_mismatch",
                        existing_dim=existing_size,
                        configured_dim=settings.embedding_dim,
                    )
        except Exception as exc:
            log.warning("semantic_cache.init_failed", error=str(exc))

    async def get(self, query_vector: list[float]) -> dict[str, Any] | None:
        """Search for semantically similar cached response. Non-blocking; fails open."""
        if not settings.semantic_cache_enabled:
            return None

        try:
            result = await self._client.query_points(
                collection_name=SEMANTIC_CACHE_COLLECTION,
                query=query_vector,
                limit=1,
                with_payload=True,
            )
            hits = result.points
            if hits and float(hits[0].score) >= SIMILARITY_THRESHOLD:
                payload = hits[0].payload or {}
                created_at = payload.get("created_at")
                if created_at is not None and (time.time() - float(created_at) > self._ttl_seconds):
                    log.info("semantic_cache.expired", age=time.time() - float(created_at))
                    return None
                log.info(
                    "semantic_cache.hit",
                    score=hits[0].score,
                    query=payload.get("query", "")[:50],
                )
                return payload.get("response")
        except Exception as exc:
            log.warning("semantic_cache.get_error", error=str(exc))
        return None

    async def put(
        self, query_vector: list[float], query_text: str, response: dict[str, Any]
    ) -> None:
        """Store query vector and response in semantic cache. Non-blocking; fails open."""
        if not settings.semantic_cache_enabled:
            return

        try:
            point_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS, f"{query_text}:{json.dumps(response, sort_keys=True)}"
                )
            )
            await self._client.upsert(
                collection_name=SEMANTIC_CACHE_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=query_vector,
                        payload={
                            "query": query_text,
                            "response": response,
                            "created_at": time.time(),
                        },
                    )
                ],
            )
            log.info("semantic_cache.stored", query=query_text[:50])
        except Exception as exc:
            log.warning("semantic_cache.put_error", error=str(exc))

    async def invalidate(self) -> None:
        """Purge all entries from the semantic cache collection."""
        try:
            if await self._client.collection_exists(SEMANTIC_CACHE_COLLECTION):
                await self._client.delete_collection(SEMANTIC_CACHE_COLLECTION)
                await self.init()
                log.info("semantic_cache.invalidated")
        except Exception as exc:
            log.warning("semantic_cache.invalidate_failed", error=str(exc))

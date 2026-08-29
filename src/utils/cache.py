from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.utils.config import get_settings
from src.utils.http_client import create_async_redis_client

log = structlog.get_logger(__name__)
SEMANTIC_CACHE_COLLECTION = "kraken_semantic_cache"
SIMILARITY_THRESHOLD = 0.92


def create_async_qdrant_client() -> AsyncQdrantClient:
    """Factory returning a configured AsyncQdrantClient (remote Cloud or in-memory fallback)."""
    settings = get_settings()
    if settings.qdrant_url:
        log.info("qdrant.remote_client")
        return AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            cloud_inference=settings.qdrant_cloud_inference_enabled,
        )
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
        settings = get_settings()
        self._client = client or create_async_qdrant_client()
        self._ttl_seconds = ttl_seconds
        self._redis = (
            create_async_redis_client(settings.redis_url)
            if settings.redis_url and settings.semantic_cache_enabled
            else None
        )

    def _exact_cache_key(self, query_text: str, context: dict[str, str] | None) -> str:
        normalized = " ".join(query_text.lower().split())
        context_key = json.dumps(context or {}, sort_keys=True)
        digest = hashlib.sha256(f"{normalized}:{context_key}".encode()).hexdigest()
        return f"kraken:semantic-cache:exact:{digest}"

    async def _get_exact(
        self, query_text: str | None, context: dict[str, str] | None
    ) -> dict[str, Any] | None:
        if not self._redis or not query_text:
            return None
        try:
            raw = await self._redis.get(self._exact_cache_key(query_text, context))
            if not raw:
                return None
            payload = json.loads(raw)
            if isinstance(payload, dict):
                log.info("semantic_cache.exact_hit")
                return payload
        except Exception as exc:
            log.warning("semantic_cache.exact_get_error", error=str(exc))
        return None

    async def _put_exact(
        self,
        query_text: str,
        response: dict[str, Any],
        context: dict[str, str] | None,
    ) -> None:
        if not self._redis:
            return
        try:
            await self._redis.setex(
                self._exact_cache_key(query_text, context),
                int(self._ttl_seconds),
                json.dumps(response, sort_keys=True, default=str),
            )
            log.info("semantic_cache.exact_stored")
        except Exception as exc:
            log.warning("semantic_cache.exact_put_error", error=str(exc))

    async def init(self) -> None:
        """Ensure the cache collection exists. Must be awaited during service startup."""
        settings = get_settings()
        vector_dim = (
            settings.qdrant_inference_dim
            if settings.qdrant_url and settings.qdrant_cloud_inference_enabled
            else settings.embedding_dim
        )
        try:
            if not await self._client.collection_exists(SEMANTIC_CACHE_COLLECTION):
                await self._client.create_collection(
                    collection_name=SEMANTIC_CACHE_COLLECTION,
                    vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
                )
                log.info(
                    "semantic_cache.collection_created",
                    collection=SEMANTIC_CACHE_COLLECTION,
                    size=vector_dim,
                )
            else:
                info = await self._client.get_collection(collection_name=SEMANTIC_CACHE_COLLECTION)
                vectors = info.config.params.vectors
                existing_size = getattr(vectors, "size", None)
                if isinstance(vectors, dict):
                    existing_size = vectors.get("size")
                if existing_size and existing_size != vector_dim:
                    log.error(
                        "semantic_cache.dimension_mismatch",
                        existing_dim=existing_size,
                        configured_dim=vector_dim,
                    )
            for field_name in ("embedding_model", "knowledge_version", "role", "scope"):
                try:
                    await self._client.create_payload_index(
                        collection_name=SEMANTIC_CACHE_COLLECTION,
                        field_name=field_name,
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                except Exception as exc:
                    log.debug(
                        "semantic_cache.payload_index_skipped",
                        field=field_name,
                        error=exc.__class__.__name__,
                    )
        except Exception as exc:
            log.warning("semantic_cache.init_failed", error=str(exc))

    async def get(
        self,
        query_vector: Any,
        context: dict[str, str] | None = None,
        query_text: str | None = None,
    ) -> dict[str, Any] | None:
        """Search for semantically similar cached response. Non-blocking; fails open."""
        if not get_settings().semantic_cache_enabled:
            return None

        try:
            query_filter = None
            if context:
                query_filter = Filter(
                    must=[
                        FieldCondition(key=key, match=MatchValue(value=value))
                        for key, value in context.items()
                    ]
                )
            result = await self._client.query_points(
                collection_name=SEMANTIC_CACHE_COLLECTION,
                query=query_vector,
                query_filter=query_filter,
                limit=1,
                with_payload=True,
            )
            hits = result.points
            if hits and float(hits[0].score) >= SIMILARITY_THRESHOLD:
                payload = hits[0].payload or {}
                created_at = payload.get("created_at")
                if created_at is not None and (time.time() - float(created_at) > self._ttl_seconds):
                    log.info("semantic_cache.expired", age=time.time() - float(created_at))
                    return await self._get_exact(query_text, context)
                log.info(
                    "semantic_cache.hit",
                    score=hits[0].score,
                )
                return payload.get("response")
        except Exception as exc:
            log.warning("semantic_cache.get_error", error=str(exc))
        return await self._get_exact(query_text, context)

    async def put(
        self,
        query_vector: Any,
        query_text: str,
        response: dict[str, Any],
        context: dict[str, str] | None = None,
    ) -> None:
        """Store query vector and response in semantic cache. Non-blocking; fails open."""
        if not get_settings().semantic_cache_enabled:
            return

        point_id = str(
            uuid.uuid5(uuid.NAMESPACE_DNS, f"{query_text}:{json.dumps(response, sort_keys=True)}")
        )
        try:
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
                            **(context or {}),
                        },
                    )
                ],
            )
            log.info("semantic_cache.stored")
        except Exception as exc:
            log.warning("semantic_cache.put_error", error=str(exc))
        await self._put_exact(query_text, response, context)

    async def probe(self, context: dict[str, str], vector_dim: int) -> tuple[bool, str | None]:
        """Verify semantic cache can write and read at least one backend."""
        if not get_settings().semantic_cache_enabled:
            return False, "disabled"

        query_text = "__kraken_semantic_cache_probe__"
        response = {
            "session_id": "probe",
            "answer": "semantic cache probe",
            "reasoning": "cache probe",
            "sources": ["probe"],
            "retrieved_chunks": [
                {"source": "probe", "content": "semantic cache probe", "relevance_score": 1.0}
            ],
            "cache": {"hit": False, **context},
        }
        if self._redis:
            try:
                await self._put_exact(query_text, response, context)
                cached = await self._get_exact(query_text, context)
                if cached and cached.get("answer") == response["answer"]:
                    return True, None
            except Exception:
                pass

        try:
            vector = [0.001] * vector_dim
            await self.put(vector, query_text, response, context)
            cached = await self.get(vector, context, query_text=query_text)
            if cached and cached.get("answer") == response["answer"]:
                return True, None
            return False, "cache probe miss"
        except Exception as exc:
            return False, exc.__class__.__name__

    async def invalidate(self) -> None:
        """Purge all entries from the semantic cache collection."""
        try:
            if await self._client.collection_exists(SEMANTIC_CACHE_COLLECTION):
                await self._client.delete_collection(SEMANTIC_CACHE_COLLECTION)
                await self.init()
                log.info("semantic_cache.invalidated")
        except Exception as exc:
            log.warning("semantic_cache.invalidate_failed", error=str(exc))

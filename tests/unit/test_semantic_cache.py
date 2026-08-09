"""
Unit tests for SemanticCache (shared/cache.py).

Uses AsyncQdrantClient with in-memory (:memory:) backend — zero real Qdrant dependency.
Verifies: init, hit/miss, error fail-open, collection creation on init.
"""

from __future__ import annotations

import pytest_asyncio
from qdrant_client import AsyncQdrantClient

from shared.cache import SEMANTIC_CACHE_COLLECTION, SemanticCache

_VECTOR_384 = [0.1] * 384
_RESPONSE = {"answer": "Test answer", "session_id": "s1"}


@pytest_asyncio.fixture
async def cache() -> SemanticCache:
    """In-memory async Qdrant cache, fully initialised."""
    client = AsyncQdrantClient(location=":memory:")
    c = SemanticCache(client=client)
    await c.init()
    return c


# ── init ──────────────────────────────────────────────────────────────────────


class TestInit:
    async def test_collection_created_on_init(self, cache: SemanticCache) -> None:
        exists = await cache._client.collection_exists(SEMANTIC_CACHE_COLLECTION)
        assert exists is True

    async def test_double_init_is_safe(self, cache: SemanticCache) -> None:
        """Calling init() twice must not raise (collection already exists)."""
        await cache.init()
        exists = await cache._client.collection_exists(SEMANTIC_CACHE_COLLECTION)
        assert exists is True


# ── get / put ─────────────────────────────────────────────────────────────────


class TestGetPut:
    async def test_miss_on_empty_cache(self, cache: SemanticCache) -> None:
        result = await cache.get(_VECTOR_384)
        assert result is None

    async def test_hit_after_put(self, cache: SemanticCache) -> None:
        await cache.put(_VECTOR_384, "test query", _RESPONSE)
        result = await cache.get(_VECTOR_384)
        assert result is not None
        assert result["answer"] == "Test answer"

    async def test_put_is_idempotent(self, cache: SemanticCache) -> None:
        """Upserting the same vector twice must not raise."""
        await cache.put(_VECTOR_384, "test query", _RESPONSE)
        await cache.put(_VECTOR_384, "test query", _RESPONSE)
        result = await cache.get(_VECTOR_384)
        assert result is not None


# ── fail-open behaviour ────────────────────────────────────────────────────────


class TestFailOpen:
    async def test_get_returns_none_on_qdrant_error(self) -> None:
        """get() must return None (cache miss) when Qdrant raises — fail open."""
        from unittest.mock import AsyncMock, MagicMock

        client = MagicMock(spec=AsyncQdrantClient)
        client.collection_exists = AsyncMock(return_value=True)
        client.query_points = AsyncMock(side_effect=RuntimeError("Qdrant unreachable"))

        c = SemanticCache(client=client)
        result = await c.get(_VECTOR_384)
        assert result is None

    async def test_put_silently_skips_on_qdrant_error(self) -> None:
        """put() must not raise when Qdrant is unavailable — fail open."""
        from unittest.mock import AsyncMock, MagicMock

        client = MagicMock(spec=AsyncQdrantClient)
        client.collection_exists = AsyncMock(return_value=True)
        client.upsert = AsyncMock(side_effect=RuntimeError("Qdrant unreachable"))

        c = SemanticCache(client=client)
        # Should not raise
        await c.put(_VECTOR_384, "query", _RESPONSE)

    async def test_init_silently_skips_on_qdrant_error(self) -> None:
        """init() must not raise when Qdrant is unreachable — fail open."""
        from unittest.mock import AsyncMock, MagicMock

        client = MagicMock(spec=AsyncQdrantClient)
        client.collection_exists = AsyncMock(side_effect=RuntimeError("Qdrant unreachable"))

        c = SemanticCache(client=client)
        # Should not raise
        await c.init()

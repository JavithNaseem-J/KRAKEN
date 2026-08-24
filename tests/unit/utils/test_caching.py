"""
Unit tests for SemanticCache and AsyncQdrantClient factory.
Zero external network / disk dependency.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from src.utils.cache import SemanticCache, create_async_qdrant_client


class TestSemanticCache:
    def test_cache_miss_when_disabled(self) -> None:
        mock_qdrant = AsyncMock()
        cache = SemanticCache(client=mock_qdrant)
        with patch("src.utils.cache.settings") as mock_settings:
            mock_settings.semantic_cache_enabled = False
            res = asyncio.run(cache.get([0.1] * 384))
            assert res is None

    def test_cache_invalidation(self) -> None:
        mock_qdrant = AsyncMock()
        mock_qdrant.collection_exists.return_value = True
        cache = SemanticCache(client=mock_qdrant)
        asyncio.run(cache.invalidate())
        assert mock_qdrant.delete_collection.call_count == 1


class TestQdrantClientFactory:
    def test_create_async_qdrant_client_in_memory(self) -> None:
        with patch("src.utils.cache.settings") as mock_settings:
            mock_settings.qdrant_url = ""
            client = create_async_qdrant_client()
            assert client is not None

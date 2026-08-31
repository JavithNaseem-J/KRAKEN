"""
Unit tests for SemanticCache and AsyncQdrantClient factory.
Zero external network / disk dependency.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.cache import EXACT_CACHE_GENERATION_KEY, SemanticCache, create_async_qdrant_client


class TestSemanticCache:
    def test_cache_miss_when_disabled(self) -> None:
        mock_qdrant = AsyncMock()
        cache = SemanticCache(client=mock_qdrant)
        mock_settings = MagicMock(semantic_cache_enabled=False)
        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            res = asyncio.run(cache.get([0.1] * 384))
            assert res is None

    def test_cache_invalidation(self) -> None:
        mock_qdrant = AsyncMock()
        mock_qdrant.collection_exists.return_value = True
        cache = SemanticCache(client=mock_qdrant)
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        cache._redis = mock_redis
        asyncio.run(cache.invalidate())
        assert mock_qdrant.delete_collection.call_count == 1
        mock_redis.incr.assert_awaited_once_with(EXACT_CACHE_GENERATION_KEY)

    def test_cache_init_creates_cloud_filter_indexes(self) -> None:
        mock_qdrant = AsyncMock()
        mock_qdrant.collection_exists.return_value = False
        cache = SemanticCache(client=mock_qdrant)

        asyncio.run(cache.init())

        indexed_fields = {
            call.kwargs["field_name"] for call in mock_qdrant.create_payload_index.await_args_list
        }
        assert indexed_fields == {"embedding_model", "knowledge_version", "role", "scope"}

    def test_expired_cache_entry_is_a_miss(self) -> None:
        mock_qdrant = AsyncMock()
        mock_qdrant.query_points.return_value = SimpleNamespace(
            points=[
                SimpleNamespace(
                    score=0.99,
                    payload={
                        "created_at": time.time() - 61,
                        "response": {"answer": "stale"},
                    },
                )
            ]
        )
        cache = SemanticCache(client=mock_qdrant, ttl_seconds=60)
        mock_settings = MagicMock(semantic_cache_enabled=True)

        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            assert asyncio.run(cache.get([0.1] * 384)) is None

    def test_private_cache_lookup_filters_every_context_dimension(self) -> None:
        mock_qdrant = AsyncMock()
        mock_qdrant.query_points.return_value = SimpleNamespace(points=[])
        cache = SemanticCache(client=mock_qdrant)
        context = {
            "role": "end_user",
            "scope": "session-a",
            "embedding_model": "model-a",
            "knowledge_version": "v1",
        }
        mock_settings = MagicMock(semantic_cache_enabled=True)

        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            assert asyncio.run(cache.get([0.1] * 384, context)) is None

        query_filter = mock_qdrant.query_points.await_args.kwargs["query_filter"]
        conditions = {condition.key: condition.match.value for condition in query_filter.must}
        assert conditions == context

    def test_exact_redis_cache_hits_when_qdrant_misses(self) -> None:
        mock_qdrant = AsyncMock()
        mock_qdrant.query_points.return_value = SimpleNamespace(points=[])
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = [
            b"0",
            '{"answer": "cached VPN answer", "session_id": "old"}',
        ]
        mock_settings = MagicMock(semantic_cache_enabled=True, redis_url="")
        cache = SemanticCache(client=mock_qdrant)
        cache._redis = mock_redis

        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            result = asyncio.run(
                cache.get(
                    [0.1] * 384,
                    {
                        "role": "end_user",
                        "scope": "shared",
                        "embedding_model": "model",
                        "knowledge_version": "v2",
                    },
                    query_text="How do I connect to the corporate VPN?",
                )
            )

        assert result is not None
        assert result["answer"] == "cached VPN answer"
        assert mock_redis.get.await_count == 2

    def test_exact_cache_generation_changes_key_namespace(self) -> None:
        cache = SemanticCache(client=AsyncMock())
        context = {"role": "end_user", "knowledge_version": "v2"}

        old_key = cache._exact_cache_key("VPN help", context, "0")
        new_key = cache._exact_cache_key("VPN help", context, "1")

        assert old_key != new_key

    def test_recomputed_query_context_reuses_qdrant_point_id(self) -> None:
        mock_qdrant = AsyncMock()
        cache = SemanticCache(client=mock_qdrant)
        context = {
            "role": "end_user",
            "scope": "shared",
            "embedding_model": "model",
            "knowledge_version": "v2",
        }
        mock_settings = MagicMock(semantic_cache_enabled=True)

        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            asyncio.run(cache.put([0.1] * 384, "VPN help", {"answer": "old"}, context))
            asyncio.run(cache.put([0.1] * 384, "VPN help", {"answer": "new"}, context))

        first_id = mock_qdrant.upsert.await_args_list[0].kwargs["points"][0].id
        second_id = mock_qdrant.upsert.await_args_list[1].kwargs["points"][0].id
        assert first_id == second_id

    def test_cache_strips_nested_reasoning_before_storage(self) -> None:
        mock_qdrant = AsyncMock()
        cache = SemanticCache(client=mock_qdrant)
        cache._redis = None
        mock_settings = MagicMock(semantic_cache_enabled=True)

        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            asyncio.run(
                cache.put(
                    [0.1] * 384,
                    "VPN help",
                    {
                        "answer": "safe",
                        "action_result": {"status": "done", "reasoning": "private"},
                    },
                )
            )

        stored = mock_qdrant.upsert.await_args.kwargs["points"][0].payload["response"]
        assert stored == {"answer": "safe", "action_result": {"status": "done"}}

    def test_different_cache_context_uses_distinct_qdrant_point_id(self) -> None:
        mock_qdrant = AsyncMock()
        cache = SemanticCache(client=mock_qdrant)
        mock_settings = MagicMock(semantic_cache_enabled=True)

        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            asyncio.run(
                cache.put(
                    [0.1] * 384,
                    "VPN help",
                    {"answer": "user"},
                    {"role": "end_user", "knowledge_version": "v2"},
                )
            )
            asyncio.run(
                cache.put(
                    [0.1] * 384,
                    "VPN help",
                    {"answer": "admin"},
                    {"role": "admin", "knowledge_version": "v2"},
                )
            )

        first_id = mock_qdrant.upsert.await_args_list[0].kwargs["points"][0].id
        second_id = mock_qdrant.upsert.await_args_list[1].kwargs["points"][0].id
        assert first_id != second_id


class TestQdrantClientFactory:
    def test_create_async_qdrant_client_in_memory(self) -> None:
        mock_settings = MagicMock(qdrant_url="")
        with patch("src.utils.cache.get_settings", return_value=mock_settings):
            client = create_async_qdrant_client()
            assert client is not None

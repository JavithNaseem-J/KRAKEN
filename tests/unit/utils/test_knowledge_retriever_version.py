from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.utils.knowledge.retriever import KnowledgeRetriever, settings
from src.utils.models.knowledge import KnowledgeSource, RetrievalRequest


def _hit(point_id: str, version: str, *, source: str = "faq") -> SimpleNamespace:
    return SimpleNamespace(
        id=point_id,
        score=0.99,
        payload={
            "content": "Corporate VPN connection guidance",
            "source": source,
            "document_id": f"{point_id}.md",
            "scope": "shared",
            "allowed_roles": ["public"],
            "collection_version": version,
            "metadata": {"ticket_id": "TCK-1001"} if source == "tickets" else {},
        },
    )


def _retriever(client: AsyncMock) -> KnowledgeRetriever:
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 384
    return KnowledgeRetriever(client=client, embedder=embedder)


@pytest.mark.asyncio
async def test_retrieval_excludes_stale_collection_version() -> None:
    client = AsyncMock()
    client.query_points.return_value = SimpleNamespace(
        points=[_hit("active", settings.knowledge_collection_version), _hit("stale", "v1")]
    )

    result = await _retriever(client).retrieve(
        RetrievalRequest(
            query="corporate VPN guidance",
            sources=[KnowledgeSource.FAQ],
            session_id="test-session",
        )
    )

    assert [chunk.chunk_id for chunk in result.chunks] == ["active"]
    query_filter = client.query_points.await_args.kwargs["query_filter"]
    conditions = {condition.key: condition.match for condition in query_filter.must}
    assert conditions["collection_version"].value == settings.knowledge_collection_version


@pytest.mark.asyncio
async def test_retrieval_returns_no_stale_only_result() -> None:
    client = AsyncMock()
    client.query_points.return_value = SimpleNamespace(points=[_hit("stale", "v1")])

    result = await _retriever(client).retrieve(
        RetrievalRequest(
            query="corporate VPN guidance",
            sources=[KnowledgeSource.FAQ],
            session_id="test-session",
        )
    )

    assert result.total_retrieved == 0


@pytest.mark.asyncio
async def test_ticket_scroll_uses_active_collection_version() -> None:
    client = AsyncMock()
    client.query_points.return_value = SimpleNamespace(points=[])
    client.scroll.return_value = (
        [_hit("ticket-active", settings.knowledge_collection_version, source="tickets")],
        None,
    )

    await _retriever(client).retrieve(
        RetrievalRequest(
            query="status of TCK-1001",
            sources=[KnowledgeSource.TICKETS],
            session_id="test-session",
        )
    )

    scroll_filter = client.scroll.await_args.kwargs["scroll_filter"]
    conditions = {condition.key: condition.match for condition in scroll_filter.must}
    assert conditions["collection_version"].value == settings.knowledge_collection_version

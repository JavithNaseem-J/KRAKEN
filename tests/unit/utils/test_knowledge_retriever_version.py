from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from src.utils.knowledge.ingest import ensure_collection, upsert_chunks_async
from src.utils.knowledge.loaders.sla_loader import load_sla_chunks
from src.utils.knowledge.retriever import KnowledgeRetriever, _heuristic_rerank, settings
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
            "dataset_generation": settings.synthetic_dataset_generation,
            "metadata": {"ticket_id": "TCK-24001"} if source == "tickets" else {},
        },
    )


def _retriever(client: AsyncMock) -> KnowledgeRetriever:
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 384
    return KnowledgeRetriever(client=client, embedder=embedder)


def test_exact_sla_severity_survives_relevance_threshold() -> None:
    p2 = _hit("p2", settings.knowledge_collection_version, source="sla")
    p2.payload["content"] = "SLA Severity Level: P2 (High)\nRequired Approval Level: Security Lead"
    p1 = _hit("p1", settings.knowledge_collection_version, source="sla")
    p1.payload["content"] = (
        "SLA Severity Level: P1 (Critical)\nRequired Approval Level: Incident Commander"
    )
    ranked = _heuristic_rerank("Who approves P2 containment work?", [(p2, 0.03), (p1, 0.029)])
    assert ranked[0][0].id == "p2"
    assert ranked[0][1] >= 0.4


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
    assert conditions["dataset_generation"].value == settings.synthetic_dataset_generation


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
            query="status of TCK-24001",
            sources=[KnowledgeSource.TICKETS],
            session_id="test-session",
        )
    )

    scroll_filter = client.scroll.await_args.kwargs["scroll_filter"]
    conditions = {condition.key: condition.match for condition in scroll_filter.must}
    assert conditions["collection_version"].value == settings.knowledge_collection_version
    assert conditions["dataset_generation"].value == settings.synthetic_dataset_generation


@pytest.mark.asyncio
async def test_synthetic_ticket_id_does_not_expand_to_numeric_seed_ids() -> None:
    client = AsyncMock()
    client.query_points.return_value = SimpleNamespace(
        points=[_hit("unrelated-seed", settings.knowledge_collection_version, source="tickets")]
    )
    client.scroll.return_value = ([], None)

    result = await _retriever(client).retrieve(
        RetrievalRequest(
            query="status of ticket SYN-E3AD3A2BE183",
            sources=[KnowledgeSource.TICKETS],
            session_id="test-session",
        )
    )

    assert result.total_retrieved == 0
    scroll_filter = client.scroll.await_args.kwargs["scroll_filter"]
    ticket_condition = next(
        condition for condition in scroll_filter.must if condition.key == "metadata.ticket_id"
    )
    assert ticket_condition.match.any == ["SYN-E3AD3A2BE183"]


@pytest.mark.asyncio
async def test_disposable_qdrant_only_returns_current_sla_risk_knowledge() -> None:
    client = AsyncQdrantClient(location=":memory:")
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * settings.embedding_dim
    embedder.embed_documents.side_effect = lambda texts: [
        [0.1] * settings.embedding_dim for _ in texts
    ]
    try:
        await ensure_collection(client, settings.qdrant_collection_name)
        chunks = load_sla_chunks()
        assert any("quarantine_ip: CRITICAL" in chunk["document"] for chunk in chunks)
        await upsert_chunks_async(client, embedder, chunks, KnowledgeSource.SLA.value)
        await client.upsert(
            collection_name=settings.qdrant_collection_name,
            points=[
                PointStruct(
                    id=str(uuid4()),
                    vector=[0.1] * settings.embedding_dim,
                    payload={
                        "content": "obsolete risk mapping",
                        "source": KnowledgeSource.SLA.value,
                        "scope": "shared",
                        "allowed_roles": ["public"],
                        "collection_version": "v2",
                        "dataset_generation": settings.synthetic_dataset_generation,
                    },
                )
            ],
        )
        result = await KnowledgeRetriever(client, embedder).retrieve(
            RetrievalRequest(
                query="quarantine_ip risk mapping",
                sources=[KnowledgeSource.SLA],
                session_id="disposable-session",
            )
        )
        assert any("quarantine_ip: CRITICAL" in chunk.content for chunk in result.chunks)
        assert all("obsolete risk mapping" not in chunk.content for chunk in result.chunks)
    finally:
        await client.close()

"""
Integration tests for the knowledge retriever.
Uses an in-memory ChromaDB client — no disk I/O, no embedder model needed.
"""

from __future__ import annotations

import chromadb
import pytest
from chromadb import Documents, EmbeddingFunction, Embeddings

from services.knowledge.retriever import KnowledgeRetriever, _source_to_collection_name
from shared.models.knowledge import KnowledgeSource, RetrievalRequest


class FakeEmbedder(EmbeddingFunction[Documents]):
    """Returns a fixed 3-dim vector — avoids loading sentence-transformers in tests."""

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        return [[0.1, 0.2, 0.3]] * len(input)


@pytest.fixture
def in_memory_retriever() -> KnowledgeRetriever:
    client = chromadb.EphemeralClient()
    embedder = FakeEmbedder()
    collections = {}

    for source in KnowledgeSource:
        name = _source_to_collection_name(source)
        col = client.get_or_create_collection(
            name=name,
            embedding_function=embedder,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )
        collections[name] = col

    # Seed FAQ collection with one document
    faq_col = collections[_source_to_collection_name(KnowledgeSource.FAQ)]
    faq_col.upsert(
        ids=["faq_test_0001"],
        documents=["VPN policy: all users must use the company VPN when working remotely."],
        metadatas=[
            {"source": "faq", "file": "test_policy.md", "chunk_index": 0, "total_chunks": 1}
        ],
    )

    return KnowledgeRetriever(client=client, collections=collections)


@pytest.mark.asyncio
async def test_retrieve_returns_results(in_memory_retriever: KnowledgeRetriever) -> None:
    request = RetrievalRequest(
        query="VPN remote work policy",
        sources=[KnowledgeSource.FAQ],
        top_k=3,
        session_id="test-session",
    )
    result = await in_memory_retriever.retrieve(request)
    assert result.total_retrieved == 1
    assert result.chunks[0].source == KnowledgeSource.FAQ
    assert result.chunks[0].chunk_id == "faq_test_0001"


@pytest.mark.asyncio
async def test_empty_source_returns_gracefully(in_memory_retriever: KnowledgeRetriever) -> None:
    """SLA collection is empty — should return 0 chunks, not an exception."""
    request = RetrievalRequest(
        query="escalation policy",
        sources=[KnowledgeSource.SLA],
        top_k=3,
        session_id="test-session",
    )
    result = await in_memory_retriever.retrieve(request)
    assert result.total_retrieved == 0
    assert result.chunks == []


@pytest.mark.asyncio
async def test_multi_source_deduplication(in_memory_retriever: KnowledgeRetriever) -> None:
    """Multi-source query should not duplicate chunks."""
    request = RetrievalRequest(
        query="VPN policy",
        sources=[KnowledgeSource.FAQ, KnowledgeSource.TICKETS, KnowledgeSource.SLA],
        top_k=5,
        session_id="test-session",
    )
    result = await in_memory_retriever.retrieve(request)
    chunk_ids = [c.chunk_id for c in result.chunks]
    assert len(chunk_ids) == len(set(chunk_ids)), "Duplicate chunks detected"


@pytest.mark.asyncio
async def test_relevance_scores_between_0_and_1(in_memory_retriever: KnowledgeRetriever) -> None:
    request = RetrievalRequest(
        query="VPN",
        sources=[KnowledgeSource.FAQ],
        top_k=1,
        session_id="test-session",
    )
    result = await in_memory_retriever.retrieve(request)
    for chunk in result.chunks:
        assert 0.0 <= chunk.relevance_score <= 1.0

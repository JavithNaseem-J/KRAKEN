from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.knowledge import app, settings
from src.utils.models.knowledge import KnowledgeChunk, KnowledgeSource, RetrievalResult

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    # Mock lifespan dependencies (BAAI embedder and Qdrant client)
    mock_embedder = MagicMock()
    mock_qdrant = AsyncMock()
    mock_qdrant.count.return_value = SimpleNamespace(count=1)
    mock_retriever = AsyncMock()

    with (
        patch("src.utils.embedder.get_embedder", return_value=mock_embedder),
        patch("src.utils.cache.create_async_qdrant_client", return_value=mock_qdrant),
        patch("src.api.knowledge.KnowledgeRetriever", return_value=mock_retriever),
        patch("src.utils.knowledge.ingest.ensure_collection", new_callable=AsyncMock),
        TestClient(app) as c,
    ):
        c.app.state.retriever = mock_retriever
        yield c


@pytest.mark.parametrize("active_count,expected_ingests", [(0, 1), (1, 0)])
def test_startup_ingests_when_active_knowledge_is_absent(
    active_count: int, expected_ingests: int
) -> None:
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collection.return_value = SimpleNamespace(points_count=12)
    mock_qdrant.count.return_value = SimpleNamespace(count=active_count)

    with (
        patch("src.utils.embedder.get_embedder", return_value=MagicMock()),
        patch("src.utils.cache.create_async_qdrant_client", return_value=mock_qdrant),
        patch("src.utils.knowledge.ingest.ensure_collection", new_callable=AsyncMock),
        patch("src.utils.knowledge.ingest.run_ingest_async", new_callable=AsyncMock) as ingest,
        TestClient(app),
    ):
        assert app.state.client is mock_qdrant

    assert ingest.await_count == expected_ingests
    conditions = {
        condition.key: condition.match.value
        for condition in mock_qdrant.count.await_args.kwargs["count_filter"].must
    }
    assert conditions == {
        "collection_version": settings.knowledge_collection_version,
        "dataset_generation": settings.synthetic_dataset_generation,
    }


class TestKnowledgeAPI:
    def test_health_check(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "ok"

    def test_retrieve_requires_auth(self, client) -> None:
        response = client.post(
            "/retrieve",
            json={
                "query": "SLA rules",
                "sources": ["faq"],
                "top_k": 3,
                "session_id": "s1",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "service token" in response.json()["detail"].lower()

    def test_retrieve_authorized_success(self, client) -> None:
        client.app.state.retriever.retrieve.return_value = RetrievalResult(
            chunks=[
                KnowledgeChunk(
                    content="SLA is 4 hours",
                    source=KnowledgeSource.SLA,
                    relevance_score=0.9,
                    document_id="doc1",
                    chunk_id="chunk1",
                    metadata={},
                )
            ],
            query="SLA rules",
            total_retrieved=1,
            sources_queried=[KnowledgeSource.SLA],
        )

        response = client.post(
            "/retrieve",
            json={
                "query": "SLA rules",
                "sources": ["sla"],
                "top_k": 3,
                "session_id": "s1",
            },
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total_retrieved"] == 1

    def test_ingest_requires_auth(self, client) -> None:
        response = client.post("/ingest")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("src.utils.knowledge.ingest.run_ingest_async", new_callable=AsyncMock)
    def test_ingest_success(self, mock_run: AsyncMock, client) -> None:
        mock_run.return_value = {"faq": 10, "tickets": 5, "sla": 2}

        response = client.post(
            "/ingest",
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["faq"] == 10

    @patch("src.utils.cache.SemanticCache.invalidate", new_callable=AsyncMock)
    @patch("src.utils.knowledge.ingest.run_ingest_async", new_callable=AsyncMock)
    def test_ingest_invalidates_semantic_cache(
        self, mock_run: AsyncMock, mock_invalidate: AsyncMock, client
    ) -> None:
        mock_run.return_value = {"faq": 10, "tickets": 5, "sla": 2}

        response = client.post(
            "/ingest",
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK
        assert mock_invalidate.called

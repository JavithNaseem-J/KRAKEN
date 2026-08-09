from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.knowledge.main import app
from shared.models.knowledge import KnowledgeChunk, KnowledgeSource, RetrievalResult

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    # Mock lifespan dependencies (BAAI embedder and Qdrant client)
    mock_embedder = MagicMock()
    mock_qdrant = AsyncMock()
    mock_retriever = AsyncMock()

    with (
        patch("services.knowledge.main.BGEEmbedder", return_value=mock_embedder),
        patch("shared.cache.create_async_qdrant_client", return_value=mock_qdrant),
        TestClient(app) as c,
    ):
        c.app.state.retriever = mock_retriever
        yield c


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

    @patch("services.knowledge.ingest.run_ingest_async", new_callable=AsyncMock)
    def test_ingest_success(self, mock_run: AsyncMock, client) -> None:
        mock_run.return_value = {"faq": 10, "tickets": 5, "sla": 2}

        response = client.post(
            "/ingest",
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["faq"] == 10

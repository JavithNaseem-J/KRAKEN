"""
Unit tests for the Knowledge Service API.
Mocks embedding model, ChromaDB, and retrievers — zero network / disk dependency.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.knowledge.main import app


@pytest.fixture
def client():
    # Mock lifespan dependencies (BAAI embedder and Chroma client)
    mock_embedder = MagicMock()
    mock_chroma = MagicMock()
    mock_retriever = AsyncMock()

    with (
        patch("services.knowledge.main.BGEEmbedder", return_value=mock_embedder),
        patch("services.knowledge.main.chromadb.PersistentClient", return_value=mock_chroma),
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
        client.app.state.retriever.retrieve.return_value = {
            "chunks": [
                {
                    "content": "SLA is 4 hours",
                    "source": "sla",
                    "relevance_score": 0.9,
                    "document_id": "doc1",
                    "chunk_id": "chunk1",
                    "metadata": {},
                }
            ],
            "query": "SLA rules",
            "total_retrieved": 1,
            "sources_queried": ["sla"],
        }

        response = client.post(
            "/retrieve",
            json={
                "query": "SLA rules",
                "sources": ["sla"],
                "top_k": 3,
                "session_id": "s1",
            },
            headers={"X-Service-Token": "change-me-in-production"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total_retrieved"] == 1

    def test_ingest_requires_auth(self, client) -> None:
        response = client.post("/ingest")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("services.knowledge.main._run_ingest")
    def test_ingest_success(self, mock_run: MagicMock, client) -> None:
        mock_run.return_value = {"faq": 10, "tickets": 5, "sla": 2}

        response = client.post(
            "/ingest",
            headers={"X-Service-Token": "change-me-in-production"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["faq"] == 10

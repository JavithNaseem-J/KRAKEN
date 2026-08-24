"""
Unit tests for AKEA Orchestrator nodes and API endpoints.
Uses mock databases, HTTP clients, and LLMs — zero external dependencies.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.agent.nodes.memory_writer import memory_writer_node
from src.agent.nodes.retriever import retriever_node
from src.api.orchestrator import app

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


# ── Retriever Node Tests ──────────────────────────────────────────────────────
class TestRetrieverNode:
    @patch("src.agent.nodes.retriever.httpx.AsyncClient")
    def test_retriever_http_success(self, mock_client_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chunks": [{"content": "http info", "source": "web"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        state = {
            "session_id": "s1",
            "user_message": "Hello http",
        }

        result = asyncio.run(retriever_node(state))
        assert len(result["retrieved_chunks"]) >= 1
        assert result["retrieved_chunks"][0]["source"] == "web"

        # Verify X-Service-Token was passed in HTTP headers
        args, kwargs = mock_client.post.call_args
        assert "X-Service-Token" in kwargs["headers"]


# ── Memory Writer Node Tests ──────────────────────────────────────────────────
class TestMemoryWriterNode:
    async def test_memory_writer_node_non_blocking(self) -> None:
        state = {
            "session_id": "s1",
            "user_message": "Hello",
            "messages": [],
            "final_answer": "Answer",
            "selected_action": "auto_respond",
        }
        res = await memory_writer_node(state)
        assert res == {}


# ── API Endpoint Tests ────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    # Mock lifespan requirements (Postgres connection pool, Graph building, Reaper task)
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value.execute = MagicMock()

    mock_graph = MagicMock()

    with (
        patch("src.api.orchestrator.validate_llm_config"),
        patch("src.api.orchestrator.ConnectionPool", return_value=mock_pool),
        patch("src.api.orchestrator.build_graph_async", return_value=mock_graph),
        TestClient(app) as c,
    ):
        c.app.state.conn_pool = mock_pool
        c.app.state.agent_graph = mock_graph
        yield c


class TestOrchestratorAPI:
    def test_health_endpoint_healthy(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] is True

    def test_health_endpoint_degraded(self, client) -> None:
        client.app.state.conn_pool.connection.side_effect = Exception("DB Connection failed")
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] is False

    def test_callback_requires_auth(self, client) -> None:
        response = client.post(
            "/approval-callback", json={"approval_id": "a1", "decision": "approve"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "service token" in response.json()["detail"].lower()

    def test_callback_not_found(self, client) -> None:
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        client.app.state.conn_pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        response = client.post(
            "/approval-callback",
            json={"approval_id": "nonexistent-id", "decision": "approve"},
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_prune_stale_checkpoints_runs_cleanly(self) -> None:
        from src.api.orchestrator import prune_stale_checkpoints

        mock_pool = MagicMock()
        mock_cur = MagicMock()
        mock_cur.rowcount = 5
        mock_pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        counts = prune_stale_checkpoints(mock_pool)
        assert "checkpoints" in counts
        assert "checkpoint_writes" in counts




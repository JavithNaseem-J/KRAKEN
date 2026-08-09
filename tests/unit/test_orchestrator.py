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

from services.orchestrator.graph.nodes.decider import decider_node
from services.orchestrator.graph.nodes.memory_writer import memory_writer_node
from services.orchestrator.graph.nodes.retriever import retriever_node
from services.orchestrator.main import app

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


# ── Decider Node Tests ────────────────────────────────────────────────────────
class TestDeciderNode:
    @patch("services.orchestrator.graph.nodes.decider.get_llm")
    def test_decider_valid_action(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        decision_mock = MagicMock()
        decision_mock.selected_action = "auto_respond"
        decision_mock.selected_actions = None
        decision_mock.action_payload = {"ticket_id": "T1", "response_text": "text"}
        decision_mock.evidence = "Some evidence"
        decision_mock.explanation = "Some explanation"

        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=decision_mock)
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "Hello",
            "reasoning": "Reasoning context",
        }

        result = asyncio.run(decider_node(state))
        assert result["selected_action"] == "auto_respond"
        assert result["risk_level"] == "SAFE"
        assert result["evidence"] == "Some evidence"
        assert result["action_payload"]["ticket_id"] == "T1"
        assert result["action_payload"]["evidence"] == "Some evidence"

    @patch("services.orchestrator.graph.nodes.decider.get_llm")
    def test_decider_rejects_hallucinated_action(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        decision_mock = MagicMock()
        decision_mock.selected_action = "hallucinated_action_name"
        decision_mock.selected_actions = None
        decision_mock.action_payload = {}
        decision_mock.evidence = "evidence"
        decision_mock.explanation = "explanation"

        mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=decision_mock)
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "Hello",
            "reasoning": "Context",
        }

        result = asyncio.run(decider_node(state))
        assert result["selected_action"] is None
        assert "error" in result
        assert "hallucinated" in result["error"]


# ── Retriever Node Tests ──────────────────────────────────────────────────────
class TestRetrieverNode:
    @patch("services.orchestrator.graph.nodes.retriever.httpx.AsyncClient")
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
        patch("services.orchestrator.main.validate_llm_config"),
        patch("services.orchestrator.main.ConnectionPool", return_value=mock_pool),
        patch("services.orchestrator.main.build_graph_async", return_value=mock_graph),
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




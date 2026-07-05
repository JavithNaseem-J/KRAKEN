"""
Unit tests for AKEA Orchestrator nodes and API endpoints.
Uses mock databases, HTTP clients, and LLMs — zero external dependencies.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.orchestrator.graph.nodes.decider import decider_node
from services.orchestrator.graph.nodes.memory_writer import memory_writer_node
from services.orchestrator.graph.nodes.retriever import retriever_node
from services.orchestrator.main import app


# ── Decider Node Tests ────────────────────────────────────────────────────────
class TestDeciderNode:
    @patch("services.orchestrator.graph.nodes.decider.get_llm")
    def test_decider_valid_action(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        decision_mock = MagicMock()
        decision_mock.selected_action = "auto_respond"
        decision_mock.action_payload = {"ticket_id": "T1", "response_text": "text"}
        decision_mock.evidence = "Some evidence"
        decision_mock.explanation = "Some explanation"

        mock_llm.with_structured_output.return_value.invoke.return_value = decision_mock
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "Hello",
            "reasoning": "Reasoning context",
        }

        result = decider_node(state)
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
        decision_mock.action_payload = {}
        decision_mock.evidence = "evidence"
        decision_mock.explanation = "explanation"

        mock_llm.with_structured_output.return_value.invoke.return_value = decision_mock
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "Hello",
            "reasoning": "Context",
        }

        result = decider_node(state)
        assert result["selected_action"] is None
        assert "error" in result
        assert "hallucinated" in result["error"]


# ── Retriever Node Tests ──────────────────────────────────────────────────────
class TestRetrieverNode:
    @patch("services.orchestrator.graph.nodes.retriever._redis_client")
    @patch("services.orchestrator.graph.nodes.retriever._http_client")
    def test_retriever_cache_hit(self, mock_http: MagicMock, mock_redis: MagicMock) -> None:
        cached_chunks = [{"content": "cached info", "source": "docs", "relevance_score": 0.95}]
        mock_redis.get.return_value = json.dumps(cached_chunks)

        state = {
            "session_id": "s1",
            "user_message": "Hello cached",
        }

        result = retriever_node(state)
        assert result["retrieved_chunks"] == cached_chunks
        mock_http.post.assert_not_called()

    @patch("services.orchestrator.graph.nodes.retriever._redis_client")
    @patch("services.orchestrator.graph.nodes.retriever._http_client")
    def test_retriever_cache_miss_http_success(
        self, mock_http: MagicMock, mock_redis: MagicMock
    ) -> None:
        mock_redis.get.return_value = None

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"chunks": [{"content": "http info", "source": "web"}]}
        mock_resp.raise_for_status = MagicMock()
        mock_http.post.return_value = mock_resp

        state = {
            "session_id": "s1",
            "user_message": "Hello http",
        }

        result = retriever_node(state)
        assert len(result["retrieved_chunks"]) == 1
        assert result["retrieved_chunks"][0]["source"] == "web"

        # Verify X-Service-Token was passed in HTTP headers
        args, kwargs = mock_http.post.call_args
        assert "X-Service-Token" in kwargs["headers"]
        assert mock_redis.set.called


# ── Memory Writer Node Tests ──────────────────────────────────────────────────
class TestMemoryWriterNode:
    @patch("services.orchestrator.graph.nodes.memory_writer._http_client")
    @patch("services.orchestrator.graph.nodes.memory_writer._thread_pool")
    def test_memory_writer_submits_to_pool(
        self, mock_pool: MagicMock, mock_http: MagicMock
    ) -> None:
        state = {
            "session_id": "s1",
            "user_message": "Hello",
            "messages": [],
            "final_answer": "Answer",
            "selected_action": "auto_respond",
        }
        memory_writer_node(state)
        assert mock_pool.submit.called


# ── API Endpoint Tests ────────────────────────────────────────────────────────
_TOKEN = "change-me-in-production"
_HEADERS = {"X-Service-Token": _TOKEN}


@pytest.fixture
def client():
    # Mock lifespan requirements (Postgres connection pool, Graph building, Reaper task)
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value.execute = MagicMock()

    mock_graph = MagicMock()

    with (
        patch("services.orchestrator.main.validate_llm_config"),
        patch("services.orchestrator.main.ConnectionPool", return_value=mock_pool),
        patch("services.orchestrator.main.build_graph", return_value=mock_graph),
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

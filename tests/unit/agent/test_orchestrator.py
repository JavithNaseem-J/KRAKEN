"""
Unit tests for AKEA Orchestrator nodes and API endpoints.
Uses mock databases, HTTP clients, and LLMs — zero external dependencies.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.agent.nodes.memory_writer import _persist_memory, memory_writer_node
from src.agent.nodes.retriever import retriever_node
from src.api.orchestrator import _casual_response, _schedule_background_task, app, run, run_stream
from src.utils.models.agent import QueryRequest

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

    @patch("src.agent.nodes.retriever.internal_request")
    @patch("src.agent.nodes.retriever._fetch_knowledge", new_callable=AsyncMock)
    async def test_public_session_skips_shared_episodic_memory(
        self, mock_fetch: AsyncMock, mock_internal: AsyncMock
    ) -> None:
        mock_fetch.return_value = []
        state = {
            "session_id": "public-session",
            "public_session_id": "public-session",
            "user_id": "alice",
            "user_message": "What happened earlier?",
        }

        await retriever_node(state)

        mock_internal.assert_not_awaited()


# ── Memory Writer Node Tests ──────────────────────────────────────────────────
class TestMemoryWriterNode:
    @patch("src.agent.nodes.memory_writer._persist_memory", new_callable=AsyncMock)
    async def test_memory_writer_node_schedules_persistence(self, mock_persist: AsyncMock) -> None:
        state = {
            "session_id": "s1",
            "user_message": "Hello",
            "messages": [],
            "final_answer": "Answer",
            "selected_action": "auto_respond",
        }
        res = await memory_writer_node(state)
        assert res == {}
        mock_persist.assert_not_awaited()
        await asyncio.sleep(0)
        mock_persist.assert_awaited_once()

    @patch("src.utils.http_client.post_with_retry", new_callable=AsyncMock)
    async def test_public_session_persists_only_short_term_memory(
        self, mock_post: AsyncMock
    ) -> None:
        await _persist_memory(
            AsyncMock(),
            "public-session",
            "alice",
            [],
            "Question",
            "Answer",
            "auto_respond",
            None,
            None,
            store_episodic=False,
        )

        assert mock_post.await_count == 1
        assert "/session/public-session" in mock_post.await_args.args[1]


class TestLatencyFastPath:
    @staticmethod
    def _request(message: str) -> QueryRequest:
        return QueryRequest(session_id="latency-session", user_id="anonymous", message=message)

    def test_exact_greeting_has_a_deterministic_response(self) -> None:
        response = _casual_response(self._request(" Hi! "))

        assert response is not None
        assert response.answer.startswith("Hello!")
        assert response.action_taken is None
        assert response.retrieved_chunks == []
        assert response.execution_ms == 0

    def test_substantive_request_is_not_a_casual_message(self) -> None:
        assert _casual_response(self._request("Hi, create a ticket for a broken laptop")) is None

    async def test_sync_greeting_bypasses_graph_initialization(self) -> None:
        with patch("src.api.orchestrator._get_graph", new_callable=AsyncMock) as get_graph:
            response = await run(self._request("hello"))

        assert response.answer.startswith("Hello!")
        get_graph.assert_not_awaited()

    async def test_streamed_greeting_bypasses_graph_initialization(self) -> None:
        with patch("src.api.orchestrator._get_graph", new_callable=AsyncMock) as get_graph:
            response = await run_stream(self._request("thanks"))
            events = []
            async for chunk in response.body_iterator:
                for line in chunk.splitlines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))

        assert len(events) == 1
        assert events[0]["node"] == "done"
        assert events[0]["response"]["answer"].startswith("You're welcome")
        get_graph.assert_not_awaited()

    async def test_background_task_does_not_block_the_caller(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_persistence() -> None:
            started.set()
            await release.wait()

        _schedule_background_task(
            slow_persistence(), task_name="test-persistence", session_id="latency-session"
        )
        await asyncio.wait_for(started.wait(), timeout=0.1)
        assert release.is_set() is False
        release.set()
        await asyncio.sleep(0)

    async def test_stream_forwards_only_responder_chunks_and_final_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeGraph:
            def __init__(self) -> None:
                self.state_calls = 0

            async def aget_state(self, _config):
                self.state_calls += 1
                if self.state_calls == 1:
                    return SimpleNamespace(next=[], values={})
                return SimpleNamespace(
                    next=[],
                    values={"final_answer": "Hello world", "selected_action": None},
                )

            async def astream_events(self, *_args, **_kwargs):
                yield {"event": "on_chain_start", "name": "reasoner"}
                yield {
                    "event": "on_chat_model_stream",
                    "name": "ChatOpenAI",
                    "metadata": {"langgraph_node": "reasoner"},
                    "data": {"chunk": SimpleNamespace(content="private reasoning")},
                }
                yield {
                    "event": "on_chat_model_stream",
                    "name": "ChatOpenAI",
                    "metadata": {"langgraph_node": "responder"},
                    "data": {"chunk": SimpleNamespace(content="Hello")},
                }
                yield {
                    "event": "on_chat_model_stream",
                    "name": "ChatOpenAI",
                    "metadata": {"langgraph_node": "responder"},
                    "data": {"chunk": SimpleNamespace(content=" world")},
                }

        graph = FakeGraph()

        async def fake_get_graph(**_kwargs):
            return graph, {}

        async def no_cache(_body):
            return None, None, None

        async def no_history(*_args, **_kwargs):
            return []

        def discard_background(coroutine, **_kwargs):
            coroutine.close()

        monkeypatch.setattr("src.api.orchestrator._get_graph", fake_get_graph)
        monkeypatch.setattr("src.api.orchestrator._semantic_cache_lookup", no_cache)
        monkeypatch.setattr("src.api.orchestrator._fetch_session_messages", no_history)
        monkeypatch.setattr("src.api.orchestrator._schedule_background_task", discard_background)

        response = await run_stream(self._request("How do I use VPN?"))
        payload = "".join([chunk async for chunk in response.body_iterator])
        events = [json.loads(line[6:]) for line in payload.splitlines() if line.startswith("data: ")]

        deltas = [event["content"] for event in events if event["status"] == "delta"]
        assert deltas == ["Hello", " world"]
        assert "private reasoning" not in payload
        assert events[-1]["response"]["answer"] == "".join(deltas)


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

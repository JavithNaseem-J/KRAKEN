"""
Unit tests for the Memory Service HTTP API.
Patches ShortTermMemory and LongTermMemory so no real Redis or Postgres is needed.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from qdrant_client.models import Document

from src.api.memory import app
from src.utils.memory.long_term import LongTermMemory

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}

_MSGS = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"},
]


def test_cloud_long_term_memory_does_not_load_local_embedder() -> None:
    cloud_settings = SimpleNamespace(
        qdrant_url="https://qdrant.example",
        qdrant_cloud_inference_enabled=True,
        qdrant_inference_model="sentence-transformers/all-MiniLM-L6-v2",
        qdrant_inference_dim=384,
        embedding_dim=384,
    )
    with (
        patch("src.utils.memory.long_term.settings", cloud_settings),
        patch("src.utils.embedder.get_embedder") as get_local_embedder,
    ):
        memory = LongTermMemory(client=AsyncMock())
        vector = asyncio.run(memory._embed_async("private episodic query"))

    assert isinstance(vector, Document)
    get_local_embedder.assert_not_called()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "cloud")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("POSTGRES_URL", "")
    monkeypatch.setenv("POSTGRES_SYNC_URL", "")
    """
    Boot the app with ShortTermMemory completely mocked so no Redis is needed.
    Long-term memory is set to None to simulate Postgres being unavailable.
    """
    mock_stm = MagicMock()
    mock_stm.ping = AsyncMock(return_value=True)
    mock_stm.get_session = AsyncMock(return_value=_MSGS)
    mock_stm.update_session = AsyncMock()
    mock_stm.append_messages = AsyncMock(
        return_value=_MSGS + [{"role": "user", "content": "Extra"}]
    )
    mock_stm.clear_session = AsyncMock()
    mock_stm.close = AsyncMock()

    with (
        patch("src.api.memory.ShortTermMemory", return_value=mock_stm),
        patch("src.api.memory.create_async_qdrant_client", side_effect=Exception("no qdrant")),
        patch("src.api.memory.create_pool", side_effect=Exception("no postgres in tests")),
        TestClient(app) as c,
    ):
        c.app.state.short_term = mock_stm
        c.app.state.long_term = None
        c.app.state.db_pool = None
        yield c


# ── Health ────────────────────────────────────────────────────────────────────
def test_health_degraded_without_long_term(client):
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "degraded"
    assert data["short_term"] is True
    assert data["long_term"] is False


# ── Short-term auth enforcement ───────────────────────────────────────────────
def test_get_session_unauthorized(client):
    response = client.get("/session/s1")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_post_session_unauthorized(client):
    response = client.post("/session/s1", json={"messages": []})
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_append_session_unauthorized(client):
    response = client.post("/session/s1/append", json={"messages": []})
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_delete_session_unauthorized(client):
    response = client.delete("/session/s1")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ── Short-term authorized requests ────────────────────────────────────────────
def test_get_session_authorized(client):
    response = client.get("/session/s1", headers=_HEADERS)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["session_id"] == "s1"
    assert data["turns"] == 2


def test_update_session_authorized(client):
    response = client.post(
        "/session/s1",
        json={"messages": _MSGS},
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "updated"
    client.app.state.short_term.update_session.assert_called_once()


def test_append_session_authorized(client):
    response = client.post(
        "/session/s1/append",
        json={"messages": [{"role": "user", "content": "Extra"}]},
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "appended"
    assert response.json()["turns"] == 3


def test_clear_session_authorized(client):
    response = client.delete("/session/s1", headers=_HEADERS)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "cleared"
    client.app.state.short_term.clear_session.assert_called_once_with("s1")


# ── Long-term unavailable (503) ───────────────────────────────────────────────
def test_store_episode_503_when_no_postgres(client):
    response = client.post(
        "/long-term",
        json={"session_id": "s1", "user_id": "u1", "content": "test memory"},
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_search_episodes_503_when_no_postgres(client):
    response = client.post(
        "/long-term/search",
        json={"query": "test", "user_id": "u1"},
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

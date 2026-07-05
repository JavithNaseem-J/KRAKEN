"""
Unit tests for the Memory Service HTTP API.
Patches ShortTermMemory and LongTermMemory so no real Redis or Postgres is needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.memory.main import app

_TOKEN = "change-me-in-production"
_HEADERS = {"X-Service-Token": _TOKEN}

_MSGS = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"},
]


@pytest.fixture
def client():
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
        patch("services.memory.main.ShortTermMemory", return_value=mock_stm),
        patch("services.memory.main.create_pool", side_effect=Exception("no postgres in tests")),
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

"""Session memory API behavior without external services."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.memory import app

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}
_MSGS = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    memory = MagicMock()
    memory.ping = AsyncMock(return_value=True)
    memory.get_session = AsyncMock(return_value=_MSGS)
    memory.update_session = AsyncMock()
    memory.append_messages = AsyncMock(return_value=_MSGS)
    memory.clear_session = AsyncMock()
    memory.close = AsyncMock()
    with patch("src.api.memory.ShortTermMemory", return_value=memory), TestClient(app) as http:
        yield http


def test_health_reflects_session_store(client):
    assert client.get("/health").json() == {"status": "ok", "service": "memory", "short_term": True}
    client.app.state.short_term.ping = AsyncMock(return_value=False)
    assert client.get("/health").json()["status"] == "degraded"


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/session/s1", None),
        ("POST", "/session/s1", {"messages": []}),
        ("POST", "/session/s1/append", {"messages": []}),
        ("DELETE", "/session/s1", None),
    ],
)
def test_session_requires_service_token(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 403


def test_session_operations(client):
    assert client.get("/session/s1", headers=_HEADERS).json()["turns"] == 2
    assert (
        client.post("/session/s1", json={"messages": _MSGS}, headers=_HEADERS).json()["status"]
        == "updated"
    )
    assert (
        client.post("/session/s1/append", json={"messages": _MSGS}, headers=_HEADERS).json()[
            "status"
        ]
        == "appended"
    )
    assert client.delete("/session/s1", headers=_HEADERS).json()["status"] == "cleared"


def test_removed_episodic_endpoints_are_absent(client):
    assert client.post("/long-term", json={}, headers=_HEADERS).status_code == 404
    assert client.post("/long-term/search", json={}, headers=_HEADERS).status_code == 404

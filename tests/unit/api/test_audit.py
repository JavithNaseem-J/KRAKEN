"""
Unit tests for the Audit Service API.
Mocks asyncpg pool and AuditStore — zero DB / network dependency.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.audit import app

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    mock_store = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()  # Must be awaitable since lifespan calls await db_pool.close()

    # create_pool is an async function, so it must return an awaitable (AsyncMock)
    with patch("src.api.audit.create_pool", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_pool
        # Patch configure_logging to prevent global logging side effects in pytest
        with patch("src.api.audit.configure_logging"), TestClient(app) as c:
            c.app.state.store = mock_store
            c.app.state.db_pool = mock_pool
            yield c


class TestAuditAPI:
    def test_health_healthy(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["db"] is True

    def test_health_degraded(self, client) -> None:
        client.app.state.store = None
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "degraded"
        assert data["db"] is False

    def test_log_requires_auth(self, client) -> None:
        response = client.post(
            "/log",
            json={
                "session_id": "s1",
                "user_id": "u1",
                "action_type": "READ",
                "action_name": "auto_respond",
                "risk_level": "SAFE",
                "hitl_required": False,
                "status": "success",
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "service token" in response.json()["detail"].lower()

    def test_log_authorized_success(self, client) -> None:
        client.app.state.store.log_action.return_value = 42

        response = client.post(
            "/log",
            json={
                "session_id": "s1",
                "user_id": "u1",
                "action_type": "READ",
                "action_name": "auto_respond",
                "risk_level": "SAFE",
                "hitl_required": False,
                "status": "success",
            },
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == 42

    def test_session_history_unauthenticated(self, client) -> None:
        response = client.get("/history/s1")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_session_history_limit_capped(self, client) -> None:
        client.app.state.store.get_session_history.return_value = []

        response = client.get(
            "/history/s1?limit=300",
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify limit was capped at 200
        client.app.state.store.get_session_history.assert_called_once_with("s1", limit=200)

    def test_user_history_unauthenticated(self, client) -> None:
        response = client.get("/history/user/u1")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_history_limit_capped(self, client) -> None:
        client.app.state.store.get_user_history.return_value = []

        response = client.get(
            "/history/user/u1?limit=300",
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify limit was capped at 200
        client.app.state.store.get_user_history.assert_called_once_with("u1", limit=200)

    def test_verify_chain_endpoint(self, client) -> None:
        client.app.state.store.verify_chain.return_value = {"valid": True, "count": 10}

        response = client.get(
            "/verify-chain",
            headers=_HEADERS,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["valid"] is True
        assert data["count"] == 10

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.approval import app

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    mock_queue = MagicMock()
    mock_queue.ping = AsyncMock(return_value=True)
    mock_queue.stats = AsyncMock(return_value=0)
    mock_queue.enqueue = AsyncMock(return_value="test-approval-id")
    mock_queue.get = AsyncMock(
        return_value={
            "approval_id": "test-approval-id",
            "action_name": "write_json_file",
            "payload": {"data": "test"},
            "reasoning": "testing",
            "session_id": "session-123",
            "expires_at": "2026-07-05T12:00:00Z",
        }
    )
    mock_queue.resolve = AsyncMock(
        return_value={"approval_id": "test-approval-id", "session_id": "session-123"}
    )
    mock_queue.set_csrf_token = AsyncMock()
    mock_queue.verify_csrf_token = AsyncMock(return_value=True)
    mock_queue.close = AsyncMock()

    with (
        patch("src.api.approval.ApprovalQueue", return_value=mock_queue),
        TestClient(app) as c,
    ):
            c.app.state.queue = mock_queue
            c.app.state.http = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = status.HTTP_200_OK
            c.app.state.http.post = AsyncMock(return_value=mock_resp)
            c.app.state.http.aclose = AsyncMock()
            yield c


def test_health_healthy(client):
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "approval"


def test_queue_stats(client):
    client.app.state.queue.stats.return_value = 5
    response = client.get("/queue/stats", headers=_HEADERS)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["pending_approvals"] == 5


def test_pending_creation_unauthorized(client):
    response = client.post("/pending", json={"action_name": "test", "session_id": "s1"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_pending_creation_malformed(client):
    response = client.post(
        "/pending",
        json={"reasoning": "missing required action_name"},
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_pending_creation_success(client):
    response = client.post(
        "/pending",
        json={
            "action_name": "write_json_file",
            "payload": {"hello": "world"},
            "reasoning": "to store data",
            "session_id": "session-123",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["approval_id"] == "test-approval-id"
    client.app.state.queue.enqueue.assert_called_once_with(
        action_name="write_json_file",
        payload={"hello": "world"},
        reasoning="to store data",
        session_id="session-123",
    )


def test_approval_page_success(client):
    response = client.get("/approve/test-approval-id")
    assert response.status_code == status.HTTP_200_OK
    assert b"Review Pending Action" in response.content


def test_approval_page_not_found(client):
    client.app.state.queue.get.return_value = None
    response = client.get("/approve/non-existent-id")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_submit_decision_success(client):
    mock_resp = MagicMock()
    mock_resp.status_code = status.HTTP_200_OK
    client.app.state.http.post.return_value = mock_resp

    response = client.post(
        "/approve/test-approval-id/decision",
        data={"decision": "approve", "csrf_token": "valid-csrf-token"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert b"Decision Recorded" in response.content or b"approve" in response.content.lower()

    client.app.state.queue.resolve.assert_called_once_with("test-approval-id")

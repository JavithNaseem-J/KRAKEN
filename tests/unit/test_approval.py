from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.approval.main import app


@pytest.fixture
def client():
    # Patch ApprovalQueue to prevent real connection attempts during lifespan
    with patch("services.approval.main.ApprovalQueue") as mock_queue_cls:
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
        mock_queue.close = AsyncMock()
        mock_queue_cls.return_value = mock_queue

        with TestClient(app) as c:
            # Override state properties AFTER lifespan context starts
            c.app.state.queue = mock_queue
            c.app.state.http = MagicMock()
            c.app.state.http.post = AsyncMock()
            c.app.state.http.aclose = AsyncMock()
            yield c


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok", "service": "approval"}


def test_queue_stats(client):
    client.app.state.queue.stats.return_value = 5
    response = client.get("/queue/stats")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["pending_approvals"] == 5


def test_pending_creation_unauthorized(client):
    response = client.post("/pending", json={"action_name": "test", "session_id": "s1"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_pending_creation_malformed(client):
    response = client.post(
        "/pending",
        json={"reasoning": "missing required action_name"},
        headers={"X-Service-Token": "change-me-in-production"},
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
        headers={"X-Service-Token": "change-me-in-production"},
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
    # Mock upstream response
    mock_resp = MagicMock()
    mock_resp.status_code = status.HTTP_200_OK
    client.app.state.http.post.return_value = mock_resp

    response = client.post("/approve/test-approval-id/decision", data={"decision": "approve"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "sent"
    assert response.json()["decision"] == "approve"

    # Verify the callback notifier is dispatched
    client.app.state.queue.resolve.assert_called_once_with("test-approval-id")

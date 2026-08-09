from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.action.main import app

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    # Patch WORKSPACE_ROOT in write_handler and path_validator
    # to use a safe temp directory for test writes
    with (
        patch("services.action.handlers.write_handler.WORKSPACE_ROOT", tmp_path),
        patch("services.action.safety.path_validator.WORKSPACE_ROOT", tmp_path),
        patch("services.action.handlers.ticket_handler.WORKSPACE_ROOT", tmp_path),
        patch("services.action.handlers.ticket_handler._TICKETS_FILE", tmp_path / "tickets.json"),
    ):
        # Create a dummy tickets.json for ticket handlers
        (tmp_path / "tickets.json").write_text("[]")

        with TestClient(app) as c:
            c.app.state.http = MagicMock()
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            c.app.state.http.post = AsyncMock(return_value=mock_resp)
            c.app.state.http.aclose = AsyncMock()
            yield c


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok", "service": "action"}


def test_list_actions(client):
    response = client.get("/registry")
    assert response.status_code == status.HTTP_200_OK
    assert "auto_respond" in response.json()
    assert "write_json_file" in response.json()


def test_execute_unauthorized(client):
    response = client.post(
        "/execute",
        json={
            "action_name": "auto_respond",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {},
            "reasoning": "r",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_execute_unknown_action(client):
    response = client.post(
        "/execute",
        json={
            "action_name": "unknown_action",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {},
            "reasoning": "r",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_execute_missing_evidence(client):
    response = client.post(
        "/execute",
        json={
            "action_name": "auto_respond",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {},
            "reasoning": "r",
        },
        headers=_HEADERS,
    )
    # The action execution catches the error and returns a structured failureActionResult
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is False
    assert "evidence" in res["error"]


@patch("services.action.main.execute_auto_respond")
def test_execute_auto_respond_success(mock_handler, client):
    mock_handler.return_value = {"success": True, "details": "done"}
    response = client.post(
        "/execute",
        json={
            "action_name": "auto_respond",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {"evidence": "citing facts", "response_text": "hello"},
            "reasoning": "answering query",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    assert res["result"] == {"success": True, "details": "done"}
    mock_handler.assert_called_once_with(None, "hello", "citing facts")


def test_execute_write_json_success(client):
    response = client.post(
        "/execute",
        json={
            "action_name": "write_json_file",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {"target_path": "output.json", "content": {"key": "val"}},
            "reasoning": "saving results",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    assert res["result"]["bytes_written"] > 0
    assert "output.json" in res["result"]["resolved_path"]


def test_execute_write_json_path_traversal(client):
    response = client.post(
        "/execute",
        json={
            "action_name": "write_json_file",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {"target_path": "../escaped.json", "content": {"key": "val"}},
            "reasoning": "unsafe write",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is False
    assert "outside the allowed workspace" in res["error"]


def test_execute_write_json_invalid_extension(client):
    response = client.post(
        "/execute",
        json={
            "action_name": "write_json_file",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {"target_path": "unsafe.sh", "content": {"key": "val"}},
            "reasoning": "unsafe extension",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is False
    assert "extension '.sh' is not allowed" in res["error"]


@patch("services.action.main.execute_escalate")
def test_execute_escalate_success(mock_handler, client):
    mock_handler.return_value = {"success": True}
    response = client.post(
        "/execute",
        json={
            "action_name": "escalate",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {"ticket_id": "TK-100", "reason": "SLA breach", "evidence": "sla evidence"},
            "reasoning": "escalating",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    mock_handler.assert_called_once_with("TK-100", "SLA breach", "sla evidence")


@patch("services.action.main.execute_request_info")
def test_execute_request_info_success(mock_handler, client):
    mock_handler.return_value = {"success": True}
    response = client.post(
        "/execute",
        json={
            "action_name": "request_info",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {
                "ticket_id": "TK-100",
                "info_requested": "logs",
                "evidence": "missing details",
            },
            "reasoning": "need info",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    mock_handler.assert_called_once_with("TK-100", "logs", "missing details")


@patch("services.action.main.execute_close")
def test_execute_close_success(mock_handler, client):
    mock_handler.return_value = {"success": True}
    response = client.post(
        "/execute",
        json={
            "action_name": "close",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {"ticket_id": "TK-100", "reason": "resolved", "evidence": "fix confirmed"},
            "reasoning": "closing",
        },
        headers=_HEADERS,
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    mock_handler.assert_called_once_with("TK-100", "resolved", "fix confirmed")

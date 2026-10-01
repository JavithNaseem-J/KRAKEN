from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import fakeredis.aioredis
import httpx
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.action import app, settings
from src.utils.approval.queue import ApprovalQueue

_TOKEN = "f0a1e0e914479e4b4c31dc7d467d088a5bf51758dfff9fc062f4158620a14bd0"
_HEADERS = {"X-Service-Token": _TOKEN}


def _approved_action(client, action_name: str, payload: dict) -> str:
    approval_id = f"approved-{action_name}"
    queue = MagicMock()
    queue.get_decision = AsyncMock(
        return_value={
            "approval_id": approval_id,
            "decision": "approve",
            "action_name": action_name,
            "payload": payload,
            "session_id": "s1",
            "public_session_id": None,
            "initiator_id": "u1",
            "approver_id": "bob",
            "approver_role": "incident_commander",
            "dataset_generation": settings.synthetic_dataset_generation,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }
    )
    queue.claim_execution = AsyncMock(return_value=("claimed", None))
    queue.complete_execution = AsyncMock()
    queue.close = AsyncMock()
    client.app.state.approval_queue = queue
    return approval_id


def _execute_action(client, action_name: str, payload: dict, approval_id: str | None = None):
    body = {
        "action_name": action_name,
        "session_id": "s1",
        "user_id": "u1",
        "payload": payload,
    }
    if approval_id is not None:
        body["approval_id"] = approval_id
    return client.post("/execute", json=body, headers=_HEADERS)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    with (
        patch("src.safety.path_validator.WORKSPACE_ROOT", tmp_path),
        patch("src.tools.ticket.WORKSPACE_ROOT", tmp_path),
        patch("src.tools.ticket._TICKETS_FILE", tmp_path / "tickets.json"),
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
    assert "get_ticket_status" in response.json()
    assert "quarantine_ip" in response.json()


def test_execute_unauthorized(client):
    response = client.post(
        "/execute",
        json={
            "action_name": "auto_respond",
            "session_id": "s1",
            "user_id": "u1",
            "payload": {},
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
        },
        headers=_HEADERS,
    )
    # The action execution catches the error and returns a structured failureActionResult
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "Action execution failed."


@patch("src.api.action.execute_auto_respond")
def test_execute_auto_respond_success(mock_handler, client):
    mock_handler.return_value = {"success": True, "details": "done"}
    response = _execute_action(
        client, "auto_respond", {"evidence": "citing facts", "response_text": "hello"}
    )
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    assert res["result"] == {"success": True, "details": "done"}
    mock_handler.assert_called_once_with(None, "hello", "citing facts")


@patch("src.api.action.execute_get_ticket_status")
def test_execute_get_ticket_status_success(mock_handler, client):
    mock_handler.return_value = {
        "success": True,
        "ticket_id": "TCK-24001",
        "status": "OPEN",
    }
    response = _execute_action(client, "get_ticket_status", {"ticket_id": "TCK-24001"})

    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    assert res["result"]["status"] == "OPEN"
    mock_handler.assert_called_once_with("TCK-24001")


def test_direct_critical_call_without_approval_is_rejected(client):
    response = _execute_action(client, "quarantine_ip", {"ip": "203.0.113.10"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    "field,value",
    [
        ("decision", "reject"),
        ("action_name", "unlock_account"),
        ("session_id", "other-session"),
        ("public_session_id", "other-public-session"),
        ("dataset_generation", "old-generation"),
        ("approver_role", "end_user"),
        ("approver_id", "u1"),
        ("expires_at", "2020-01-01T00:00:00+00:00"),
    ],
)
def test_critical_execution_rejects_invalid_decision_binding(client, field, value):
    payload = {"ip": "203.0.113.10"}
    approval_id = _approved_action(client, "quarantine_ip", payload)
    record = client.app.state.approval_queue.get_decision.return_value
    record[field] = value
    with patch("src.api.action._dispatch") as dispatch:
        response = _execute_action(client, "quarantine_ip", payload, approval_id)
    assert response.status_code == 403
    dispatch.assert_not_called()


def test_critical_execution_rejects_unavailable_shared_decision(client):
    approval_id = _approved_action(client, "quarantine_ip", {"ip": "203.0.113.10"})
    client.app.state.approval_queue.get_decision.side_effect = ConnectionError("down")
    response = _execute_action(client, "quarantine_ip", {"ip": "203.0.113.10"}, approval_id)
    assert response.status_code == 503


@patch("src.api.action.execute_escalate")
def test_execute_escalate_success(mock_handler, client):
    mock_handler.return_value = {"success": True}
    payload = {"ticket_id": "TK-100", "reason": "SLA breach", "evidence": "sla evidence"}
    approval_id = _approved_action(client, "escalate", payload)
    response = _execute_action(client, "escalate", payload, approval_id)
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    mock_handler.assert_called_once_with("TK-100", "SLA breach", "sla evidence")


@patch("src.api.action.execute_request_info")
def test_execute_request_info_success(mock_handler, client):
    mock_handler.return_value = {"success": True}
    payload = {
        "ticket_id": "TK-100",
        "info_requested": "logs",
        "evidence": "missing details",
    }
    approval_id = _approved_action(client, "request_info", payload)
    response = _execute_action(client, "request_info", payload, approval_id)
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    mock_handler.assert_called_once_with("TK-100", "logs", "missing details")


@patch("src.api.action.execute_close")
def test_execute_close_success(mock_handler, client):
    mock_handler.return_value = {"success": True}
    payload = {"ticket_id": "TK-100", "reason": "resolved", "evidence": "fix confirmed"}
    approval_id = _approved_action(client, "close", payload)
    response = _execute_action(client, "close", payload, approval_id)
    assert response.status_code == status.HTTP_200_OK
    res = response.json()
    assert res["success"] is True
    mock_handler.assert_called_once_with("TK-100", "resolved", "fix confirmed")


@pytest.mark.asyncio
async def test_critical_execution_uses_shared_decision_and_replays_result(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = fakeredis.aioredis.FakeRedis(
        server=fakeredis.FakeServer(), decode_responses=True
    )
    app.state.approval_queue = queue
    app.state.http = MagicMock()
    payload = {"ip": "203.0.113.10", "reason": "Incident"}
    approval_id = await queue.enqueue(
        action_name="quarantine_ip",
        payload=payload,
        session_id="s1",
        initiator_id="u1",
        approval_id="shared-decision-1",
    )
    await queue.resolve(
        approval_id,
        decision="approve",
        approver_id="bob",
        approver_role="incident_commander",
    )
    request = {
        "action_name": "quarantine_ip",
        "session_id": "s1",
        "user_id": "u1",
        "approval_id": approval_id,
        "payload": payload,
    }
    with (
        patch(
            "src.api.action._dispatch", return_value={"success": True, "synthetic": True}
        ) as dispatch,
        patch("src.api.action.fire_audit_log", new_callable=AsyncMock) as audit,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post("/execute", json=request, headers=_HEADERS)
            repeated = await client.post("/execute", json=request, headers=_HEADERS)

    assert first.status_code == 200
    assert repeated.json() == first.json()
    dispatch.assert_called_once_with("quarantine_ip", payload)
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["hitl_decision"] == "approved"
    assert audit.await_args.kwargs["result"]["approval"]["approver_id"] == "bob"
    await queue.close()


@pytest.mark.asyncio
async def test_changed_payload_cannot_use_approved_critical_action(monkeypatch):
    monkeypatch.setenv("HITL_SERVICE_TOKEN", _TOKEN)
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = fakeredis.aioredis.FakeRedis(
        server=fakeredis.FakeServer(), decode_responses=True
    )
    app.state.approval_queue = queue
    approval_id = await queue.enqueue(
        action_name="quarantine_ip",
        payload={"ip": "203.0.113.10"},
        session_id="s1",
        initiator_id="u1",
        approval_id="shared-decision-2",
    )
    await queue.resolve(
        approval_id,
        decision="approve",
        approver_id="bob",
        approver_role="incident_commander",
    )
    with patch("src.api.action._dispatch") as dispatch:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/execute",
                json={
                    "action_name": "quarantine_ip",
                    "session_id": "s1",
                    "user_id": "u1",
                    "approval_id": approval_id,
                    "payload": {"ip": "203.0.113.20"},
                },
                headers=_HEADERS,
            )
    assert response.status_code == 403
    dispatch.assert_not_called()
    await queue.close()

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agent.nodes.responder import responder_node
from src.api.orchestrator import _build_response


def _streaming_answer(content: str, captured_messages: list) -> object:
    async def fake_stream(_llm, messages):
        captured_messages.append(messages)
        yield AIMessage(content=content)

    return fake_stream


@pytest.mark.asyncio
async def test_responder_node_auto_executed_approval_status():
    """Verify responder node does NOT claim human approval on auto_respond actions."""
    mock_llm = MagicMock()
    captured_messages = []
    mock_stream = _streaming_answer(
        "**SECURITY OPERATION RESPONSE**\n\n### **SUMMARY**\nVerified.\n\n### **ACTION TAKEN**\nAnswered user inquiry.\n\n### **RESULTS**\nDone.\n\n### **EVIDENCE CITED**\n- Policy doc.\n\n### **APPROVAL STATUS**\nAuto-executed; no human approval required.",
        captured_messages,
    )

    state = {
        "session_id": "test-session-123",
        "user_message": "How do I configure VPN?",
        "reasoning": "Standard knowledge lookup.",
        "selected_action": "auto_respond",
        "action_result": None,
        "approval_status": None,
        "evidence": "Policy doc Section 1",
    }

    with (
        patch("src.agent.nodes.responder.get_llm", return_value=mock_llm),
        patch("src.agent.nodes.responder.stream_llm", mock_stream),
    ):
        result = await responder_node(state)
        assert "final_answer" in result
        system_msg = captured_messages[0][0].content
        # Ensure the prompt didn't inject "Human approval WAS GRANTED"
        assert "Human approval WAS GRANTED" not in system_msg
        assert "Auto-executed; no human approval required" in system_msg
        assert "NET-01" not in system_msg


@pytest.mark.asyncio
async def test_responder_node_approved_hitl_action():
    """A successful critical action has a receipt based on its result."""
    mock_llm = MagicMock()
    captured_messages = []
    mock_stream = _streaming_answer(
        "**SECURITY OPERATION RESPONSE**\n\n### **SUMMARY**\nExecuted.\n\n### **ACTION TAKEN**\nQuarantined IP.\n\n### **RESULTS**\nBlocked.\n\n### **EVIDENCE CITED**\n- Incident policy.\n\n### **APPROVAL STATUS**\nHuman approval was granted by an authorized security operator.",
        captured_messages,
    )

    state = {
        "session_id": "test-session-456",
        "user_message": "Block IP 192.168.1.50",
        "reasoning": "Suspicious activity.",
        "selected_action": "quarantine_ip",
        "action_result": {"success": True, "ip": "192.168.1.50"},
        "approval_status": "approved",
        "evidence": "Incident policy Section 2",
    }

    with (
        patch("src.agent.nodes.responder.get_llm", return_value=mock_llm),
        patch("src.agent.nodes.responder.stream_llm", mock_stream),
    ):
        result = await responder_node(state)
        assert "Approval was granted" in result["final_answer"]
        assert "quarantine_ip: completed successfully" in result["final_answer"]
        assert "Transaction ID" not in result["final_answer"]
        assert captured_messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approval_status", "action_result", "expected", "forbidden"),
    [
        (
            "approved",
            {"success": False, "error": "Action execution failed."},
            "execution failed",
            "completed successfully",
        ),
        (
            None,
            {"success": True, "result": {"message": "Ticket created", "synthetic": True}},
            "No human approval was required",
            "Approval was granted",
        ),
        (
            "reject",
            {"cancelled": True, "reason": "Human decision: reject"},
            "not executed",
            "completed successfully",
        ),
        (
            "approved",
            {"success": True, "result": {"message": "Synthetic action", "synthetic": True}},
            "synthetic environment state only",
            "Transaction ID",
        ),
    ],
)
async def test_action_receipt_reports_only_verified_outcome(
    approval_status, action_result, expected, forbidden
):
    state = {
        "session_id": "receipt-session",
        "selected_action": "quarantine_ip" if approval_status else "create_ticket",
        "action_result": action_result,
        "approval_status": approval_status,
    }
    with patch("src.agent.nodes.responder.get_llm") as mock_llm:
        response = await responder_node(state)
    assert expected in response["final_answer"]
    assert forbidden not in response["final_answer"]
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_created_ticket_receipt_shows_the_id_for_follow_up() -> None:
    response = await responder_node(
        {
            "session_id": "receipt-session",
            "selected_action": "create_ticket",
            "action_result": {
                "action_name": "create_ticket",
                "success": True,
                "result": {"ticket_id": "SYN-E3AD3A2BE183", "synthetic": True, "success": True},
            },
        }
    )

    assert "Ticket ID: SYN-E3AD3A2BE183" in response["final_answer"]
    assert "No human approval was required" in response["final_answer"]


@pytest.mark.asyncio
async def test_action_receipt_separates_mixed_results():
    result = await responder_node(
        {
            "session_id": "mixed-session",
            "selected_action": "create_ticket",
            "approval_status": "approved",
            "action_result": [
                {"action_name": "create_ticket", "success": True, "result": {"message": "Created"}},
                {"action_name": "quarantine_ip", "success": False, "error": "Execution failed"},
            ],
        }
    )
    assert "create_ticket: completed successfully" in result["final_answer"]
    assert "quarantine_ip: execution failed" in result["final_answer"]
    assert "quarantine_ip: completed successfully" not in result["final_answer"]


def test_build_response_unique_trace_id():
    """Verify _build_response produces a unique trace_id while retaining session_id."""
    state = {
        "final_answer": "Hello",
        "reasoning": "Test reasoning",
        "selected_action": "auto_respond",
        "action_result": None,
        "retrieved_chunks": [],
    }

    resp1 = _build_response("session-1", state)
    resp2 = _build_response("session-1", state)

    assert resp1.session_id == "session-1"
    assert resp2.session_id == "session-1"
    assert resp1.trace_id != resp2.trace_id  # Unique UUIDs per execution
    assert len(resp1.trace_id) == 36

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agent.nodes.responder import responder_node
from src.api.orchestrator import _build_response


@pytest.mark.asyncio
async def test_responder_node_auto_executed_approval_status():
    """Verify responder node does NOT claim human approval on auto_respond actions."""
    mock_llm = MagicMock()
    mock_invoke = AsyncMock(
        return_value=AIMessage(
            content="**SECURITY OPERATION RESPONSE**\n\n### **SUMMARY**\nVerified.\n\n### **ACTION TAKEN**\nAnswered user inquiry.\n\n### **RESULTS**\nDone.\n\n### **EVIDENCE CITED**\n- Policy doc.\n\n### **APPROVAL STATUS**\nAuto-executed; no human approval required."
        )
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
        patch("src.agent.nodes.responder.invoke_llm", mock_invoke),
    ):
        result = await responder_node(state)
        assert "final_answer" in result
        call_args = mock_invoke.await_args.args[1]
        system_msg = call_args[0].content
        # Ensure the prompt didn't inject "Human approval WAS GRANTED"
        assert "Human approval WAS GRANTED" not in system_msg
        assert "Auto-executed; no human approval required" in system_msg
        assert "NET-01" not in system_msg


@pytest.mark.asyncio
async def test_responder_node_approved_hitl_action():
    """Verify responder node confirms human approval only when approval_status is explicitly 'approved'."""
    mock_llm = MagicMock()
    mock_invoke = AsyncMock(
        return_value=AIMessage(
            content="**SECURITY OPERATION RESPONSE**\n\n### **SUMMARY**\nExecuted.\n\n### **ACTION TAKEN**\nQuarantined IP.\n\n### **RESULTS**\nBlocked.\n\n### **EVIDENCE CITED**\n- Incident policy.\n\n### **APPROVAL STATUS**\nHuman approval was granted by an authorized security operator."
        )
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
        patch("src.agent.nodes.responder.invoke_llm", mock_invoke),
    ):
        _ = await responder_node(state)
        call_args = mock_invoke.await_args.args[1]
        system_msg = call_args[0].content
        assert "Human approval WAS GRANTED" in system_msg


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

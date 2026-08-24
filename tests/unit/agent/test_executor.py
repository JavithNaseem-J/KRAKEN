"""
Unit tests for the Executor node (src.agent.nodes.executor).
All tests run with zero network calls and mocked HTTP / LangGraph interrupts.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.nodes.executor import executor_node


class TestExecutorNode:
    @patch("src.agent.nodes.executor._call_action_service")
    def test_safe_actions_dispatched_concurrently(self, mock_call_action: AsyncMock) -> None:
        mock_call_action.return_value = {"success": True, "result": "done"}

        state = {
            "session_id": "s1",
            "selected_actions": [
                {"action_name": "auto_respond", "action_payload": {}, "risk_level": "SAFE"},
                {"action_name": "auto_respond", "action_payload": {}, "risk_level": "SAFE"},
            ],
            "risk_level": "SAFE",
            "reasoning": "Safe response",
            "user_id": "tier1_analyst",
        }
        result = asyncio.run(executor_node(state))

        assert result["approval_status"] is None
        assert isinstance(result["action_result"], list)
        assert len(result["action_result"]) == 2
        assert mock_call_action.call_count == 2

    @patch("src.agent.nodes.executor.interrupt")
    @patch("src.agent.nodes.executor._register_approval")
    def test_critical_action_pauses_with_interrupt(
        self, mock_register: AsyncMock, mock_interrupt: MagicMock
    ) -> None:
        mock_register.return_value = "appr-123"
        # interrupt resumes with reject for this test
        mock_interrupt.return_value = {"decision": "reject"}

        state = {
            "session_id": "s1",
            "selected_actions": [
                {
                    "action_name": "create_ticket",
                    "action_payload": {"user_name": "Alice"},
                    "risk_level": "CRITICAL",
                }
            ],
            "risk_level": "CRITICAL",
            "reasoning": "Ticket creation requires approval",
            "user_id": "tier1_analyst",
        }
        result = asyncio.run(executor_node(state))

        mock_register.assert_awaited_once()
        expected_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                'kraken:s1::create_ticket:{"user_name": "Alice"}',
            )
        )
        assert mock_register.await_args.kwargs["approval_id"] == expected_id
        mock_interrupt.assert_called_once_with(
            {
                "approval_id": "appr-123",
                "action_name": "create_ticket",
                "payload": {"user_name": "Alice"},
            }
        )
        assert result["approval_status"] == "reject"
        assert result["action_result"]["cancelled"] is True

    @patch("src.agent.nodes.executor._call_action_service")
    @patch("src.agent.nodes.executor.interrupt")
    @patch("src.agent.nodes.executor._register_approval")
    def test_approved_critical_action_executes(
        self,
        mock_register: AsyncMock,
        mock_interrupt: MagicMock,
        mock_call_action: AsyncMock,
    ) -> None:
        mock_register.return_value = "appr-456"
        mock_interrupt.return_value = {"decision": "approve"}
        mock_call_action.return_value = {"success": True, "ticket_id": "TCK-2000"}

        state = {
            "session_id": "s1",
            "selected_actions": [
                {
                    "action_name": "quarantine_ip",
                    "action_payload": {"ip": "1.2.3.4"},
                    "risk_level": "CRITICAL",
                }
            ],
            "risk_level": "CRITICAL",
            "reasoning": "IP quarantine approval",
            "user_id": "security_lead",
        }
        result = asyncio.run(executor_node(state))

        assert result["approval_status"] == "approved"
        assert result["action_result"]["success"] is True
        assert result["action_result"]["ticket_id"] == "TCK-2000"
        mock_call_action.assert_awaited_once()

    @patch("src.agent.nodes.executor.interrupt")
    @patch("src.agent.nodes.executor._register_approval")
    def test_rejected_critical_action_returns_cancelled(
        self, mock_register: AsyncMock, mock_interrupt: MagicMock
    ) -> None:
        mock_register.return_value = "appr-789"
        mock_interrupt.return_value = {"decision": "deny"}

        state = {
            "session_id": "s1",
            "selected_actions": [
                {
                    "action_name": "unlock_account",
                    "action_payload": {"user_email": "user@xiarch.com"},
                    "risk_level": "CRITICAL",
                }
            ],
            "risk_level": "CRITICAL",
            "reasoning": "Account unlock",
            "user_id": "tier1_analyst",
        }
        result = asyncio.run(executor_node(state))

        assert result["approval_status"] == "deny"
        assert result["action_result"]["cancelled"] is True
        assert "Human decision: deny" in result["action_result"]["reason"]

    def test_empty_actions_returns_none(self) -> None:
        state = {
            "session_id": "s1",
            "selected_actions": [],
            "selected_action": None,
            "risk_level": "SAFE",
        }
        result = asyncio.run(executor_node(state))

        assert result["action_result"] is None
        assert result["approval_status"] is None

    @patch("src.agent.nodes.executor._register_approval")
    def test_approval_registration_failure_returns_error(self, mock_register: AsyncMock) -> None:
        mock_register.side_effect = RuntimeError("Approval service unreachable")

        state = {
            "session_id": "s1",
            "selected_actions": [
                {
                    "action_name": "create_ticket",
                    "action_payload": {"user_name": "Alice"},
                    "risk_level": "CRITICAL",
                }
            ],
            "risk_level": "CRITICAL",
            "reasoning": "Failing registration",
        }
        result = asyncio.run(executor_node(state))

        assert result["approval_status"] == "failed"
        assert result["action_result"]["success"] is False
        assert "Failed to register approval request" in result["error"]

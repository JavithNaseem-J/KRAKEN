"""
Unit tests for the Decider node (src.agent.nodes.decider).
All tests run with zero network calls and mocked LLM calls.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.nodes.decider import DecisionOutput, decider_node


class TestDeciderNode:
    @patch("src.agent.nodes.decider.get_llm")
    def test_status_query_overrides_escalate_to_auto_respond(
        self, mock_get_llm: MagicMock
    ) -> None:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=DecisionOutput(
                selected_action="escalate",
                action_payload={"ticket_id": "TCK-1001", "reason": "urgency"},
                evidence="Policy citation",
                explanation="Need escalation",
            )
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "What is the status of ticket TCK-1001?",
            "reasoning": "User is inquiring about status.",
        }
        result = asyncio.run(decider_node(state))

        assert result["selected_action"] == "get_ticket_status"
        assert result["action_payload"] == {"ticket_id": "TCK-1001"}
        assert result["risk_level"] == "SAFE"
        mock_get_llm.assert_not_called()

    @patch("src.agent.nodes.decider.get_llm")
    def test_no_ticket_id_overrides_close_to_auto_respond(
        self, mock_get_llm: MagicMock
    ) -> None:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=DecisionOutput(
                selected_action="close",
                action_payload={"reason": "Customer resolved"},
                evidence="Customer email",
                explanation="Issue solved",
            )
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "Please close the ticket for me.",
            "reasoning": "User asked to close ticket but gave no ID.",
        }
        result = asyncio.run(decider_node(state))

        assert result["selected_action"] == "auto_respond"
        assert result["risk_level"] == "SAFE"

    @patch("src.agent.nodes.decider.get_llm")
    def test_ticket_id_present_allows_escalate(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=DecisionOutput(
                selected_action="escalate",
                action_payload={"ticket_id": "TCK-1001", "reason": "RCE vulnerability in production"},
                evidence="CVE-2024-9999 reported",
                explanation="Critical severity incident",
            )
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "operator_role": "tier1_analyst",
            "user_message": "Critical RCE found in TCK-1001! Escalate immediately!",
            "reasoning": "Critical vulnerability requires escalation.",
        }
        result = asyncio.run(decider_node(state))

        assert result["selected_action"] == "escalate"
        assert result["risk_level"] == "CRITICAL"

    @patch("src.agent.nodes.decider.get_llm")
    def test_policy_denies_unauthorized_action_staging(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=DecisionOutput(
                selected_action="quarantine_ip",
                action_payload={"ip": "203.0.113.10", "reason": "suspicious traffic"},
                evidence="Firewall logs",
                explanation="Block suspicious source",
            )
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "operator_role": "end_user",
            "user_message": "Quarantine IP 203.0.113.10",
            "reasoning": "User requests firewall mutation.",
        }
        result = asyncio.run(decider_node(state))

        assert result["selected_action"] is None
        assert result["risk_level"] is None
        assert "insufficient clearance" in result["error"].lower()

    @patch("src.agent.nodes.decider.get_llm")
    def test_hallucinated_action_returns_error(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=DecisionOutput(
                selected_action="launch_missiles",
                action_payload={},
                evidence="",
                explanation="Nonexistent action",
            )
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "Do something strange",
            "reasoning": "Unrecognized intent",
        }
        result = asyncio.run(decider_node(state))

        assert result["selected_action"] is None
        assert "error" in result
        assert "hallucinated unregistered action" in result["error"]

    @patch("src.agent.nodes.decider.get_llm")
    def test_create_ticket_not_overridden(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.ainvoke = AsyncMock(
            return_value=DecisionOutput(
                selected_action="create_ticket",
                action_payload={
                    "user_name": "Alice",
                    "category": "IT",
                    "priority": "P3",
                    "description": "Broken monitor replacement",
                },
                evidence="User request",
                explanation="Staging ticket creation",
            )
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "Please create a new ticket for a broken monitor replacement for Alice",
            "reasoning": "Requesting new IT ticket.",
        }
        result = asyncio.run(decider_node(state))

        assert result["selected_action"] == "create_ticket"
        assert result["risk_level"] == "CRITICAL"

    @patch("src.agent.nodes.decider.get_llm")
    def test_risk_level_from_registry_not_llm(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        # Even if the LLM thinks auto_respond is CRITICAL, the registry overrides it to SAFE
        mock_structured.ainvoke = AsyncMock(
            return_value=DecisionOutput(
                selected_action="auto_respond",
                action_payload={},
                evidence="General inquiry",
                explanation="Informational reply",
            )
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "How do I connect to VPN?",
            "reasoning": "Informational request.",
        }
        result = asyncio.run(decider_node(state))

        assert result["selected_action"] == "auto_respond"
        assert result["risk_level"] == "SAFE"

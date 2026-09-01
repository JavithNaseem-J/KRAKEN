from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.nodes.responder import responder_node


@patch("src.agent.nodes.responder.get_llm")
def test_responder_formats_ticket_status_when_llm_fails(mock_get_llm: MagicMock) -> None:
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("Connection error."))
    mock_get_llm.return_value = mock_llm

    result = asyncio.run(
        responder_node(
            {
                "session_id": "s1",
                "user_message": "What is the status of ticket TCK-24001?",
                "reasoning": "Read-only status lookup.",
                "selected_action": "get_ticket_status",
                "action_result": {
                    "action_name": "get_ticket_status",
                    "success": True,
                    "result": {
                        "action": "get_ticket_status",
                        "ticket_id": "TCK-24001",
                        "status": "OPEN",
                        "priority": "P3",
                        "subject": "GlobalProtect VPN Connection Fails",
                        "category": "VPN & Remote Access",
                        "user_id": "alice.smith",
                        "updated_at": "2026-08-07T08:30:00Z",
                        "description": "VPN fails with Error 51.",
                    },
                },
            }
        )
    )

    assert "Ticket Information: TCK-24001" in result["final_answer"]
    assert "**Status:** `OPEN`" in result["final_answer"]
    assert "Connection error" not in result["final_answer"]
    mock_get_llm.assert_not_called()


@patch("src.agent.nodes.responder.get_llm")
def test_responder_uses_retrieved_chunks_when_llm_fails(mock_get_llm: MagicMock) -> None:
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("Connection error."))
    mock_get_llm.return_value = mock_llm

    result = asyncio.run(
        responder_node(
            {
                "session_id": "s1",
                "user_message": "How do I connect to the corporate VPN?",
                "reasoning": "Reasoning unavailable.",
                "selected_action": None,
                "retrieved_chunks": [
                    {
                        "source": "faq",
                        "content": "### NET-01: GlobalProtect VPN Access\nUse GlobalProtect with MFA.",
                        "relevance_score": 0.91,
                        "metadata": {},
                    }
                ],
                "error": "llm_provider_unavailable",
            }
        )
    )

    assert "Corporate VPN Guidance" in result["final_answer"]
    assert "GlobalProtect" in result["final_answer"]
    assert "temporarily unavailable" not in result["final_answer"]


@patch("src.agent.nodes.responder.invoke_llm", new_callable=AsyncMock)
@patch("src.agent.nodes.responder.get_llm")
def test_responder_uses_standard_composition_for_vpn_question(
    mock_get_llm: MagicMock, mock_invoke: AsyncMock
) -> None:
    mock_invoke.return_value = MagicMock(
        content="### Corporate VPN Guidance\n\nUse GlobalProtect with MFA.\n\n**Sources:** faq"
    )
    result = asyncio.run(
        responder_node(
            {
                "session_id": "s1",
                "user_message": "How do I connect to the corporate VPN?",
                "reasoning": "Retrieved current VPN policy.",
                "selected_action": None,
                "retrieved_chunks": [
                    {
                        "source": "faq",
                        "content": "GlobalProtect VPN Access uses Azure AD SAML and Duo MFA.",
                        "relevance_score": 0.91,
                        "metadata": {},
                    }
                ],
            }
        )
    )

    assert "Corporate VPN Guidance" in result["final_answer"]
    assert "**Sources:** faq" in result["final_answer"]
    mock_get_llm.assert_called_once()
    mock_invoke.assert_awaited_once()


@patch("src.agent.nodes.responder.invoke_llm", new_callable=AsyncMock)
@patch("src.agent.nodes.responder.get_llm")
def test_responder_uses_standard_composition_for_sla_question(
    mock_get_llm: MagicMock, mock_invoke: AsyncMock
) -> None:
    mock_invoke.return_value = MagicMock(
        content="### Critical Vulnerability SLA Guidance\n\nP1 response: 15 minutes."
    )
    result = asyncio.run(
        responder_node(
            {
                "session_id": "s1",
                "user_message": "What is the critical vulnerability SLA?",
                "reasoning": "Retrieved current P1 SLA.",
                "selected_action": "auto_respond",
                "retrieved_chunks": [
                    {
                        "source": "sla",
                        "content": "P1 Critical Response SLA: 15 minutes. Resolution SLA: 2 hours.",
                        "relevance_score": 0.91,
                        "metadata": {},
                    }
                ],
            }
        )
    )

    assert "Critical Vulnerability SLA Guidance" in result["final_answer"]
    assert "Transaction ID" not in result["final_answer"]
    assert "Human approval was granted" not in result["final_answer"]
    mock_get_llm.assert_called_once()
    mock_invoke.assert_awaited_once()

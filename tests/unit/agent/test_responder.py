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
                "user_message": "What is the status of ticket TCK-1001?",
                "reasoning": "Read-only status lookup.",
                "selected_action": "get_ticket_status",
                "action_result": {
                    "action_name": "get_ticket_status",
                    "success": True,
                    "result": {
                        "action": "get_ticket_status",
                        "ticket_id": "TCK-1001",
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

    assert "Ticket Information: TCK-1001" in result["final_answer"]
    assert "**Status:** `OPEN`" in result["final_answer"]
    assert "Connection error" not in result["final_answer"]
    mock_get_llm.assert_not_called()

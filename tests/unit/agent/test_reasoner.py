from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from src.agent.nodes.reasoner import reasoner_node


@patch("src.agent.nodes.reasoner.get_llm")
def test_reasoner_skips_llm_for_ticket_status_query(mock_get_llm: MagicMock) -> None:
    result = asyncio.run(
        reasoner_node(
            {
                "session_id": "s1",
                "user_message": "What is the status of ticket TCK-1001?",
                "retrieved_chunks": [],
            }
        )
    )

    assert "TCK-1001" in result["reasoning"]
    assert result["insufficient_knowledge"] is False
    mock_get_llm.assert_not_called()

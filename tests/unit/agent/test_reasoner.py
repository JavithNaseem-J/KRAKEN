from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.nodes.reasoner import reasoner_node


@patch("src.agent.nodes.reasoner.invoke_llm", new_callable=AsyncMock)
@patch("src.agent.nodes.reasoner.get_llm")
def test_reasoner_uses_standard_llm_path_for_ticket_status_query(
    mock_get_llm: MagicMock, mock_invoke: AsyncMock
) -> None:
    mock_invoke.return_value = MagicMock(
        content="Use the retrieved active-generation ticket record."
    )
    result = asyncio.run(
        reasoner_node(
            {
                "session_id": "s1",
                "user_message": "What is the status of ticket TCK-24001?",
                "retrieved_chunks": [
                    {
                        "source": "ticket",
                        "content": "TCK-24001 status is OPEN.",
                        "relevance_score": 0.99,
                    }
                ],
            }
        )
    )

    assert "active-generation ticket" in result["reasoning"]
    assert result["insufficient_knowledge"] is False
    mock_get_llm.assert_called_once()
    mock_invoke.assert_awaited_once()

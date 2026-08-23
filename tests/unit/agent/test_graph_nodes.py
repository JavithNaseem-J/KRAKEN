"""
Unit tests for individual graph nodes.
All LLM calls and HTTP calls are mocked — zero network dependency.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.nodes.reasoner import reasoner_node
from src.utils.registry import get_action


# ── Reasoner ───────────────────────────────────────────────────────────────────
class TestReasonerNode:
    @patch("src.agent.nodes.reasoner.get_llm")
    def test_produces_reasoning(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="RELEVANT INFORMATION:\n- SLA is 4 hours.")
        )
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "What is the SLA for high tickets?",
            "retrieved_chunks": [
                {"content": "High: 4 hours", "source": "sla", "relevance_score": 0.9}
            ],
        }
        result = asyncio.run(reasoner_node(state))

        assert "reasoning" in result
        assert len(result["reasoning"]) > 0

    @patch("src.agent.nodes.reasoner.get_llm")
    def test_fallback_on_empty_chunks(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="No info found."))
        mock_get_llm.return_value = mock_llm

        state = {"session_id": "s1", "user_message": "anything", "retrieved_chunks": []}
        result = asyncio.run(reasoner_node(state))
        assert "reasoning" in result

    @patch("src.agent.nodes.reasoner.get_llm")
    def test_low_relevance_chunks_trigger_refusal_state(self, mock_get_llm: MagicMock) -> None:
        state = {
            "session_id": "s1",
            "user_message": "Obscure query",
            "retrieved_chunks": [
                {"content": "Irrelevant", "source": "faq", "relevance_score": 0.20}
            ],
        }
        result = asyncio.run(reasoner_node(state))
        assert result.get("insufficient_knowledge") is True
        assert "minimum relevance threshold (0.40)" in result["reasoning"]
        mock_get_llm.assert_not_called()


# ── Decider risk resolver ──────────────────────────────────────────────────────
class TestRiskResolver:
    def test_auto_respond_is_safe(self) -> None:
        assert get_action("auto_respond").risk_level.value == "SAFE"

    def test_escalate_is_critical(self) -> None:
        assert get_action("escalate").risk_level.value == "CRITICAL"

    def test_request_info_is_critical(self) -> None:
        assert get_action("request_info").risk_level.value == "CRITICAL"

    def test_close_is_critical(self) -> None:
        assert get_action("close").risk_level.value == "CRITICAL"

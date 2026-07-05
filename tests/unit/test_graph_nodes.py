"""
Unit tests for individual graph nodes.
All LLM calls and HTTP calls are mocked — zero network dependency.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.orchestrator.graph.nodes.decider import _resolve_risk_level
from services.orchestrator.graph.nodes.reasoner import reasoner_node


# ── Reasoner ───────────────────────────────────────────────────────────────────
class TestReasonerNode:
    @patch("services.orchestrator.graph.nodes.reasoner.get_llm")
    def test_produces_reasoning(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="RELEVANT INFORMATION:\n- SLA is 4 hours.")
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id": "s1",
            "user_message": "What is the SLA for high tickets?",
            "retrieved_chunks": [
                {"content": "High: 4 hours", "source": "sla", "relevance_score": 0.9}
            ],
        }
        result = reasoner_node(state)

        assert "reasoning" in result
        assert len(result["reasoning"]) > 0

    @patch("services.orchestrator.graph.nodes.reasoner.get_llm")
    def test_fallback_on_empty_chunks(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="No info found.")
        mock_get_llm.return_value = mock_llm

        state = {"session_id": "s1", "user_message": "anything", "retrieved_chunks": []}
        result = reasoner_node(state)
        assert "reasoning" in result


# ── Decider risk resolver ──────────────────────────────────────────────────────
class TestRiskResolver:
    def test_auto_respond_is_safe(self) -> None:
        assert _resolve_risk_level("auto_respond") == "SAFE"

    def test_escalate_is_critical(self) -> None:
        assert _resolve_risk_level("escalate") == "CRITICAL"

    def test_request_info_is_critical(self) -> None:
        assert _resolve_risk_level("request_info") == "CRITICAL"

    def test_close_is_critical(self) -> None:
        assert _resolve_risk_level("close") == "CRITICAL"

    def test_unknown_defaults_to_critical(self) -> None:
        """Unknown actions are treated as CRITICAL — fail-safe behaviour."""
        assert _resolve_risk_level("invented_action") == "CRITICAL"

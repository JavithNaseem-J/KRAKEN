"""
Unit tests for individual graph nodes.
All LLM calls and HTTP calls are mocked — zero network dependency.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.orchestrator.graph.nodes.planner import planner_node
from services.orchestrator.graph.nodes.reasoner import reasoner_node
from services.orchestrator.graph.nodes.decider import _resolve_risk_level


# ── Planner ────────────────────────────────────────────────────────────────────
class TestPlannerNode:
    @patch("services.orchestrator.graph.nodes.planner.get_llm")
    def test_produces_plan_steps(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="1. Retrieve relevant SLA rules.\n2. Compose an answer."
        )
        mock_get_llm.return_value = mock_llm

        state = {"session_id": "s1", "user_message": "What is the SLA for high priority tickets?"}
        result = planner_node(state)

        assert "plan_steps" in result
        assert len(result["plan_steps"]) == 2
        assert result["current_step"] == 0

    @patch("services.orchestrator.graph.nodes.planner.get_llm")
    def test_fallback_on_llm_error(self, mock_get_llm: MagicMock) -> None:
        mock_get_llm.return_value.invoke.side_effect = RuntimeError("API down")

        state = {"session_id": "s1", "user_message": "anything"}
        result = planner_node(state)

        assert result["plan_steps"] == ["Retrieve relevant knowledge and compose an answer."]
        assert "error" in result


# ── Reasoner ───────────────────────────────────────────────────────────────────
class TestReasonerNode:
    @patch("services.orchestrator.graph.nodes.reasoner.get_llm")
    def test_produces_reasoning(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="RELEVANT INFORMATION:\n- SLA is 4 hours.")
        mock_get_llm.return_value = mock_llm

        state = {
            "session_id":      "s1",
            "user_message":    "What is the SLA for high tickets?",
            "retrieved_chunks": [{"content": "High: 4 hours", "source": "sla", "relevance_score": 0.9}],
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
    def test_respond_only_is_safe(self) -> None:
        assert _resolve_risk_level("respond_only") == "SAFE"

    def test_read_actions_are_safe(self) -> None:
        assert _resolve_risk_level("read_ticket") == "SAFE"
        assert _resolve_risk_level("read_ticket_list") == "SAFE"

    def test_write_is_critical(self) -> None:
        assert _resolve_risk_level("write_json_file") == "CRITICAL"

    def test_unknown_defaults_to_critical(self) -> None:
        """Unknown actions are treated as CRITICAL — fail-safe behaviour."""
        assert _resolve_risk_level("invented_action") == "CRITICAL"

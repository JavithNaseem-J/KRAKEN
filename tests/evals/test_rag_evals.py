"""
Tests for the LLM-as-a-Judge RAG evaluator.

Validates:
  - EvaluationResult Pydantic model validates correctly
  - Evaluator produces valid scores in [0.0, 1.0] for each metric
  - Mocked evaluator produces deterministic output
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.evals.llm_judge import EvaluationResult, evaluate_rag_response


class TestEvaluationResult:
    def test_valid_scores_accepted(self) -> None:
        result = EvaluationResult(
            faithfulness=0.85,
            context_recall=0.70,
            answer_relevance=0.90,
            reasoning="All claims grounded in chunks.",
        )
        assert 0.0 <= result.faithfulness <= 1.0
        assert 0.0 <= result.context_recall <= 1.0
        assert 0.0 <= result.answer_relevance <= 1.0

    def test_boundary_scores_accepted(self) -> None:
        result = EvaluationResult(
            faithfulness=0.0,
            context_recall=1.0,
            answer_relevance=0.5,
        )
        assert result.faithfulness == 0.0
        assert result.context_recall == 1.0
        assert result.answer_relevance == 0.5

    def test_score_above_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvaluationResult(faithfulness=1.5, context_recall=0.5, answer_relevance=0.5)

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvaluationResult(faithfulness=-0.1, context_recall=0.5, answer_relevance=0.5)

    def test_default_reasoning(self) -> None:
        result = EvaluationResult(faithfulness=0.8, context_recall=0.8, answer_relevance=0.8)
        assert result.reasoning == ""


class TestEvaluateRagResponse:
    @patch("tests.evals.llm_judge._get_judge_llm")
    def test_returns_evaluation_result(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = EvaluationResult(
            faithfulness=0.92,
            context_recall=0.88,
            answer_relevance=0.85,
            reasoning="Good grounding.",
        )
        mock_get_llm.return_value = mock_llm

        result = evaluate_rag_response(
            query="What is the SLA?",
            chunks=[{"content": "SLA response is 1 hour for P1 tickets"}],
            answer="The SLA response time for P1 tickets is 1 hour.",
        )

        assert isinstance(result, EvaluationResult)
        assert 0.0 <= result.faithfulness <= 1.0
        assert 0.0 <= result.context_recall <= 1.0
        assert 0.0 <= result.answer_relevance <= 1.0

    @patch("tests.evals.llm_judge._get_judge_llm")
    def test_zero_chunks_handled(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = EvaluationResult(
            faithfulness=0.3,
            context_recall=0.1,
            answer_relevance=0.5,
        )
        mock_get_llm.return_value = mock_llm

        result = evaluate_rag_response(
            query="test query",
            chunks=[],
            answer="some answer",
        )

        assert result.faithfulness == 0.3
        assert result.context_recall == 0.1

    @patch("tests.evals.llm_judge._get_judge_llm")
    def test_invoke_called_with_messages(self, mock_get_llm: MagicMock) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = EvaluationResult(
            faithfulness=0.7,
            context_recall=0.7,
            answer_relevance=0.7,
        )
        mock_get_llm.return_value = mock_llm

        evaluate_rag_response(
            query="test",
            chunks=[{"content": "test chunk"}],
            answer="test answer",
        )

        mock_llm.invoke.assert_called_once()
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2  # system + user messages

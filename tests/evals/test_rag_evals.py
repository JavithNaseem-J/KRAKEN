"""
Tests for the LLM-as-a-Judge RAG evaluator.

Validates:
  - EvaluationResult Pydantic model validates correctly
  - Evaluator produces valid scores in [0.0, 1.0] for each metric
  - Mocked evaluator produces deterministic output
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from tests.evals.eval_harness import (
    GoldenCase,
    build_report,
    evaluate_cases,
    load_suite,
    offline_responder,
    score_response,
    write_reports,
)
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


def test_manifest_linked_suite_covers_supported_categories() -> None:
    suite, cases = load_suite()

    assert len(cases) == 50
    assert {case.category for case in cases} == set(suite.supported_categories)
    assert len({case.case_id for case in cases}) == len(cases)
    assert sum(case.source == "holdout" for case in cases) == 5


def test_duplicate_expected_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty and unique"):
        GoldenCase(
            case_id="HOLDOUT-999",
            category="knowledge_rag",
            query="question",
            expected_outcome="grounded_answer",
            required_facts=["MFA", "MFA"],
            source="holdout",
        )


def test_stale_manifest_checksum_is_rejected(tmp_path, monkeypatch) -> None:
    import tests.evals.eval_harness as harness

    raw = json.loads(harness.SUITE_PATH.read_text(encoding="utf-8"))
    raw["manifest_checksums"]["scenarios"] = "0" * 64
    stale = tmp_path / "evaluation_suite.json"
    stale.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(harness, "SUITE_PATH", stale)

    with pytest.raises(ValueError, match="checksums"):
        harness.load_suite()


def test_deterministic_scoring_rejects_reasoning_and_prohibited_claims() -> None:
    case = GoldenCase(
        case_id="HOLDOUT-999",
        category="knowledge_rag",
        query="question",
        expected_outcome="grounded_answer",
        expected_sources=["DOC-001"],
        required_facts=["MFA"],
        prohibited_claims=["secret value"],
        source="holdout",
    )

    result = score_response(
        case,
        {
            "answer": "Use MFA. secret value",
            "sources": ["DOC-001"],
            "metadata": {"reasoning": "private"},
        },
        0.25,
    )

    assert result.passed is False
    assert result.response_contract == 0.0
    assert result.prohibited_claims == ["secret value"]


def test_case_failure_does_not_stop_later_cases() -> None:
    _, cases = load_suite()
    calls = 0

    def responder(case):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError
        return offline_responder(case)

    results = evaluate_cases(cases[:2], responder)

    assert calls == 2
    assert results[0].error == "TimeoutError"
    assert results[1].passed is True


def test_optional_judge_outage_does_not_change_deterministic_score() -> None:
    _, cases = load_suite()
    case = cases[0]
    response, latency = offline_responder(case)

    with patch("tests.evals.llm_judge.evaluate_rag_response", side_effect=TimeoutError):
        result = score_response(case, response, latency, judge_enabled=True)

    assert result.passed is True
    assert result.judge.status == "unavailable"
    assert result.judge.error == "TimeoutError"


def test_reports_are_labeled_and_redacted(tmp_path, monkeypatch) -> None:
    suite, cases = load_suite()
    selected = cases[:2]
    results = evaluate_cases(selected, offline_responder)
    monkeypatch.setenv("EVAL_API_KEY", "never-write-this-key")
    report = build_report(suite, selected, results, mode="offline")
    json_path = tmp_path / "report.json"
    junit_path = tmp_path / "report.xml"

    write_reports(report, json_path, junit_path)

    serialized = json_path.read_text(encoding="utf-8")
    assert '"mode": "offline"' in serialized
    assert '"evidence_scope": "evaluator_contract_only"' in serialized
    assert "never-write-this-key" not in serialized
    assert selected[0].query not in serialized
    assert len(ET.parse(junit_path).getroot().findall("testcase")) == 2


def test_threshold_failure_marks_report_failed() -> None:
    suite, cases = load_suite()
    selected = cases[:1]
    failed = evaluate_cases(selected, lambda case: ({"answer": "unsupported"}, 0.0))

    report = build_report(suite, selected, failed, mode="live")

    assert report.status == "failed"
    assert report.mode == "live"
    assert report.evidence_scope == "observed_application_response"

"""
Tests for deterministic and RAGAS evaluation.

Validates:
  - EvaluationResult Pydantic model validates correctly
  - RAGAS receives observed chunks and reference facts
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.evals.eval_harness import (
    GoldenCase,
    build_report,
    establish_case_session,
    evaluate_cases,
    load_suite,
    make_live_responder,
    measure_stream,
    offline_responder,
    score_response,
    summarize_stream_samples,
    target_revision,
    write_reports,
)
from tests.evals.llm_judge import EvaluationResult, evaluate_rag_response


class TestEvaluationResult:
    def test_valid_scores_accepted(self) -> None:
        result = EvaluationResult(faithfulness=0.85, context_recall=0.70)
        assert 0.0 <= result.faithfulness <= 1.0
        assert 0.0 <= result.context_recall <= 1.0

    def test_boundary_scores_accepted(self) -> None:
        result = EvaluationResult(
            faithfulness=0.0,
            context_recall=1.0,
        )
        assert result.faithfulness == 0.0
        assert result.context_recall == 1.0

    def test_score_above_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvaluationResult(faithfulness=1.5, context_recall=0.5)

    def test_score_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            EvaluationResult(faithfulness=-0.1, context_recall=0.5)

    def test_missing_context_score_is_explicit(self) -> None:
        assert EvaluationResult().faithfulness is None


class TestEvaluateRagResponse:
    def test_zero_chunks_are_not_scored(self) -> None:
        result = evaluate_rag_response(query="test query", chunks=[], answer="some answer")
        assert result.faithfulness is None
        assert result.context_recall is None

    @patch("tests.evals.llm_judge.ContextRecall")
    @patch("tests.evals.llm_judge.Faithfulness")
    @patch("tests.evals.llm_judge._get_ragas_llm")
    def test_ragas_receives_real_context_and_reference(
        self, mock_llm: MagicMock, mock_faith: MagicMock, mock_recall: MagicMock
    ) -> None:
        mock_faith.return_value.score.return_value.value = 0.92
        mock_recall.return_value.score.return_value.value = 0.88
        result = evaluate_rag_response(
            query="What is the SLA?",
            chunks=[{"content": "P1 response is 1 hour"}, {"content": ""}],
            answer="P1 response is 1 hour.",
            reference_facts=["P1", "1 hour"],
        )
        assert result == EvaluationResult(faithfulness=0.92, context_recall=0.88)
        mock_faith.assert_called_once_with(llm=mock_llm.return_value)
        mock_faith.return_value.score.assert_called_once_with(
            user_input="What is the SLA?",
            response="P1 response is 1 hour.",
            retrieved_contexts=["P1 response is 1 hour"],
        )
        mock_recall.return_value.score.assert_called_once_with(
            user_input="What is the SLA?",
            retrieved_contexts=["P1 response is 1 hour"],
            reference="P1. 1 hour",
        )


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


def _live_transport(*, role: str = "tier1_analyst", sha: str = "a" * 40, stream: str | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"commit_sha": sha})
        if request.url.path == "/v1/session" and request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "session_id": "s1",
                    "csrf_token": "x" * 32,
                    "dataset_generation": "northstar-v1",
                },
                headers={"set-cookie": "session=test"},
            )
        if request.url.path == "/v1/session/persona":
            return httpx.Response(200, json={"persona": role})
        if request.url.path == "/v1/sessions/s1":
            return httpx.Response(200, json={"session_id": "s1", "persona": role})
        if request.url.path == "/v1/run/stream":
            return httpx.Response(200, text=stream or 'data: {"node":"done","status":"end"}\n\n')
        if request.url.path == "/v1/run":
            return httpx.Response(
                200,
                json={"session_id": "s1", "answer": "MFA", "sources": [], "cache": {"hit": False}},
            )
        return httpx.Response(404)

    return httpx.MockTransport(handle)


def test_live_identity_and_revision_are_verified() -> None:
    with httpx.Client(base_url="https://example.test", transport=_live_transport()) as client:
        assert target_revision(client, "a" * 40) == "a" * 40
        case = GoldenCase(
            case_id="HOLDOUT-999",
            category="knowledge_rag",
            query="MFA?",
            expected_outcome="answer",
            required_role="tier1_analyst",
            source="holdout",
        )
        result, _ = make_live_responder(client, "northstar-v1")(case)
        assert result["_verified_role"] == "tier1_analyst"
    with (
        httpx.Client(
            base_url="https://example.test", transport=_live_transport(role="end_user")
        ) as client,
        pytest.raises(ValueError, match="required role"),
    ):
        establish_case_session(client, "tier1_analyst", "northstar-v1")
    with (
        httpx.Client(
            base_url="https://example.test", transport=_live_transport(sha="0" * 40)
        ) as client,
        pytest.raises(ValueError, match="verified commit"),
    ):
        target_revision(client)
    with (
        httpx.Client(base_url="https://example.test", transport=_live_transport()) as client,
        pytest.raises(ValueError, match="does not match expected"),
    ):
        target_revision(client, "b" * 40)


def test_stream_measurement_requires_terminal_and_records_disconnect() -> None:
    payload = 'data: {"node":"responder","status":"delta","content":"Hello"}\n\ndata: {"node":"done","status":"end"}\n\n'
    with httpx.Client(
        base_url="https://example.test", transport=_live_transport(stream=payload)
    ) as client:
        complete = measure_stream(
            client, message="hello", role="tier1_analyst", generation="northstar-v1"
        )
        disconnected = measure_stream(
            client,
            message="hello",
            role="tier1_analyst",
            generation="northstar-v1",
            disconnect_after_delta=True,
        )
    assert complete["first_delta_ms"] is not None and complete["terminal_ms"] is not None
    assert complete["category"] == "greeting"
    assert disconnected["disconnected_after_delta"] is True and disconnected["terminal_ms"] is None
    assert summarize_stream_samples([complete, disconnected])["greeting"]["terminal_samples"] == 1
    with httpx.Client(
        base_url="https://example.test",
        transport=_live_transport(
            stream='data: {"node":"responder","status":"delta","content":"x"}\n\n'
        ),
    ) as client:
        assert (
            measure_stream(client, message="VPN?", role="tier1_analyst", generation="northstar-v1")[
                "error"
            ]
            == "stream ended without terminal event"
        )


def test_stream_measurement_keeps_cache_and_missing_delta_out_of_generated_samples() -> None:
    cache_events = (
        'data: {"node":"semantic_cache","status":"cache_hit"}\n\n'
        'data: {"node":"done","status":"end","response":{"answer":"Cached"}}\n\n'
    )
    with httpx.Client(
        base_url="https://example.test", transport=_live_transport(stream=cache_events)
    ) as client:
        cached = measure_stream(
            client, message="VPN?", role="tier1_analyst", generation="northstar-v1"
        )
    assert cached["category"] == "cache"
    assert cached["first_delta_ms"] is None
    assert cached["terminal_ms"] is not None
    summary = summarize_stream_samples([cached])
    assert summary["cache"]["samples"] == 1
    assert summary["cache"]["first_delta_samples"] == 0

    fallback_events = (
        'data: {"node":"done","status":"end","response":'
        '{"answer":"The AI provider is temporarily unavailable."}}\n\n'
    )
    with httpx.Client(
        base_url="https://example.test", transport=_live_transport(stream=fallback_events)
    ) as client:
        fallback = measure_stream(
            client, message="VPN?", role="tier1_analyst", generation="northstar-v1"
        )
    assert fallback["category"] == "provider_fallback"
    assert fallback["first_delta_ms"] is None

    error_event = 'data: {"node":"error","status":"error","message":"provider unavailable"}\n\n'
    with httpx.Client(
        base_url="https://example.test", transport=_live_transport(stream=error_event)
    ) as client:
        failed = measure_stream(
            client, message="VPN?", role="tier1_analyst", generation="northstar-v1"
        )
    assert failed["error"] == "provider unavailable"
    assert failed["terminal_ms"] is None


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


def test_source_name_in_answer_does_not_count_as_retrieved_source() -> None:
    case = GoldenCase(
        case_id="HOLDOUT-999",
        category="knowledge_rag",
        query="How does VPN work?",
        expected_outcome="grounded_answer",
        expected_sources=["DOC-001"],
        required_facts=["MFA"],
        source="holdout",
    )

    result = score_response(case, {"answer": "DOC-001 says MFA", "sources": []}, 0.0)

    assert result.source_recall == 0.0
    assert result.passed is False


def test_ticket_id_must_match_structured_lookup_result() -> None:
    _, cases = load_suite()
    case = next(case for case in cases if case.category == "ticket_lookup")
    response, latency = offline_responder(case)
    response["action_result"]["ticket_id"] = "SYN-WRONG"

    result = score_response(case, response, latency)

    assert result.source_recall == 0.0
    assert result.passed is False


def test_no_answer_requires_a_grounded_refusal() -> None:
    _, cases = load_suite()
    case = next(case for case in cases if case.case_id == "HOLDOUT-003")

    fabricated = score_response(
        case, {"answer": "The board earned ten million dollars.", "sources": []}, 0.0
    )
    refused = score_response(
        case,
        {
            "answer": "KRAKEN does not have enough permitted internal evidence to answer this request.",
            "sources": [],
        },
        0.0,
    )

    assert fabricated.passed is False
    assert refused.passed is True


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
    suite, cases = load_suite()
    case = cases[0]
    response, latency = offline_responder(case)
    response["retrieved_chunks"] = [{"content": "Policy response is grounded."}]

    with patch("tests.evals.llm_judge.evaluate_rag_response", side_effect=TimeoutError):
        result = score_response(case, response, latency, judge_enabled=True)

    assert result.passed is True
    assert result.judge.status == "unavailable"
    assert result.judge.error == "TimeoutError"

    report = build_report(suite, [case], [result], mode="live", judge_requested=True)
    assert report.status == "failed"


def test_ragas_requires_observed_retrieval_context() -> None:
    suite, cases = load_suite()
    case = next(case for case in cases if case.category == "knowledge_rag")
    response, latency = offline_responder(case)

    result = score_response(case, response, latency, judge_enabled=True)
    report = build_report(suite, [case], [result], mode="live", judge_requested=True)

    assert result.passed is True
    assert result.judge.status == "unavailable"
    assert report.metrics.ragas_evaluated == 0
    assert report.status == "failed"


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

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]
SUITE_PATH = ROOT / "data" / "synthetic" / "evaluation_suite.json"
SCENARIOS_PATH = ROOT / "data" / "synthetic" / "capability_scenarios.json"
MANIFEST_PATH = ROOT / "data" / "synthetic" / "manifest.json"

EvaluationCategory = Literal[
    "knowledge_rag",
    "ticket_lookup",
    "role_retrieval",
    "no_answer",
    "prompt_injection_document",
    "semantic_cache",
    "sla",
    "conflict_resolution",
    "provider_fallback",
]


class EvaluationThresholds(BaseModel):
    source_recall: float = Field(ge=0.0, le=1.0)
    required_fact_coverage: float = Field(ge=0.0, le=1.0)
    response_contract: float = Field(ge=0.0, le=1.0)
    prohibited_claim_violations: int = Field(ge=0)


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^(SCN|HOLDOUT)-\d{3}$")
    category: EvaluationCategory
    query: str = Field(min_length=1, max_length=4096)
    expected_outcome: str = Field(min_length=1)
    expected_sources: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)
    required_role: str = "tier1_analyst"
    source: Literal["manifest", "holdout"]

    @field_validator("expected_sources", "required_facts", "prohibited_claims")
    @classmethod
    def require_unique_values(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("expected values must be non-empty and unique")
        return normalized


class EvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    generation: str
    manifest_checksums: dict[str, str]
    supported_categories: list[EvaluationCategory] = Field(min_length=1)
    thresholds: EvaluationThresholds
    holdouts: list[GoldenCase]

    @model_validator(mode="after")
    def validate_holdouts(self) -> EvaluationSuite:
        if len(set(self.supported_categories)) != len(self.supported_categories):
            raise ValueError("supported_categories must be unique")
        if any(case.source != "holdout" for case in self.holdouts):
            raise ValueError("suite holdouts must declare source=holdout")
        return self


class JudgeResult(BaseModel):
    status: Literal["disabled", "available", "unavailable", "not_applicable"] = "disabled"
    faithfulness: float | None = None
    context_recall: float | None = None
    error: str | None = None


class CaseResult(BaseModel):
    case_id: str
    category: str
    passed: bool
    source_recall: float = Field(ge=0.0, le=1.0)
    required_fact_coverage: float = Field(ge=0.0, le=1.0)
    response_contract: float = Field(ge=0.0, le=1.0)
    prohibited_claims: list[str] = Field(default_factory=list)
    latency_seconds: float = Field(ge=0.0)
    error: str | None = None
    verified_role: str | None = None
    cache_hit: bool | None = None
    response_origin: str = "unknown"
    judge: JudgeResult = Field(default_factory=JudgeResult)


class EvaluationMetrics(BaseModel):
    case_pass_rate: float
    source_recall: float
    required_fact_coverage: float
    response_contract: float
    prohibited_claim_violations: int
    request_errors: int
    average_latency_seconds: float
    ragas_evaluated: int = 0
    ragas_eligible: int = 0
    ragas_faithfulness: float | None = None
    ragas_context_recall: float | None = None


class EvaluationReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["passed", "failed"]
    mode: Literal["offline", "live"]
    evidence_scope: str
    generation: str
    commit_sha: str
    provider: str | None
    model: str | None
    cache_mode: str
    excluded_count: int = 0
    case_count: int
    metrics: EvaluationMetrics
    thresholds: EvaluationThresholds
    cases: list[CaseResult]


Responder = Callable[[GoldenCase], tuple[dict[str, Any], float]]

_PROVIDER_FALLBACK_MARKERS = (
    "the ai provider is temporarily unavailable",
    "provider could not complete",
    "llm_provider_unavailable",
)


def _is_provider_fallback(answer: Any) -> bool:
    return isinstance(answer, str) and any(
        marker in answer.casefold() for marker in _PROVIDER_FALLBACK_MARKERS
    )


def load_suite() -> tuple[EvaluationSuite, list[GoldenCase]]:
    suite = EvaluationSuite.model_validate_json(SUITE_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if suite.generation != manifest.get("generation"):
        raise ValueError("evaluation generation does not match the active manifest")
    if suite.manifest_checksums != manifest.get("checksums"):
        raise ValueError("evaluation checksums do not match the active manifest")

    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    cases = [
        GoldenCase(
            case_id=scenario["scenario_id"],
            category=scenario["capability"],
            query=scenario["query"],
            expected_outcome=scenario["expected_outcome"],
            expected_sources=scenario.get("expected_sources", []),
            required_facts=scenario.get("required_facts", []),
            prohibited_claims=scenario.get("prohibited_claims", []),
            required_role=scenario.get("required_role", "tier1_analyst"),
            source="manifest",
        )
        for scenario in scenarios
        if scenario.get("capability") in suite.supported_categories
    ]
    cases.extend(suite.holdouts)

    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("evaluation case IDs must be unique")
    missing = sorted(set(suite.supported_categories) - {case.category for case in cases})
    if missing:
        raise ValueError("evaluation categories have no cases: " + ", ".join(missing))
    return suite, cases


def score_response(
    case: GoldenCase,
    response: dict[str, Any],
    latency_seconds: float,
    *,
    judge_enabled: bool = False,
) -> CaseResult:
    answer = response.get("answer")
    contract_ok = (
        isinstance(answer, str)
        and bool(answer.strip())
        and isinstance(response.get("sources", []), list)
        and not _contains_key(response, "reasoning")
    )
    serialized = json.dumps(response, sort_keys=True, default=str).casefold()
    answer_text = str(answer or "").casefold()
    cited_sources = (
        {source.casefold() for source in response["sources"] if isinstance(source, str)}
        if isinstance(response.get("sources"), list)
        else set()
    )
    action_result = response.get("action_result")
    retrieved = response.get("retrieved_chunks")
    retrieved_ids: set[str] = set()
    for chunk in retrieved if isinstance(retrieved, list) else []:
        if not isinstance(chunk, dict):
            continue
        metadata = chunk.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        for value in (
            chunk.get("document_id"),
            metadata.get("document_id"),
            metadata.get("rule_id"),
        ):
            if isinstance(value, str):
                retrieved_ids.add(value.casefold())
    source_evidence = (
        {str(action_result.get("ticket_id", "")).casefold()}
        if case.expected_outcome == "ticket_details" and isinstance(action_result, dict)
        else cited_sources | retrieved_ids
    )
    source_recall = _coverage(
        [source.casefold() in source_evidence for source in case.expected_sources]
    )
    fact_coverage = _coverage([fact.casefold() in answer_text for fact in case.required_facts])
    violations = [claim for claim in case.prohibited_claims if claim.casefold() in serialized]
    action = response.get("action_taken")
    if case.expected_outcome == "grounded_no_answer":
        outcome_ok = (
            "does not have enough permitted internal evidence" in answer_text
            and not cited_sources
            and action in (None, "auto_respond")
            and not action_result
        )
    elif case.expected_outcome == "ticket_details":
        outcome_ok = (
            action == "get_ticket_status"
            and isinstance(action_result, dict)
            and action_result.get("success") is True
            and all(source.casefold() in answer_text for source in case.expected_sources)
        )
    elif case.expected_outcome == "cache_safe_answer":
        cache = response.get("cache")
        outcome_ok = (
            isinstance(cache, dict)
            and cache.get("hit") is True
            and not _is_provider_fallback(answer)
            and action in (None, "auto_respond")
        )
    elif case.expected_outcome == "truthful_fallback":
        outcome_ok = _is_provider_fallback(answer) and action in (None, "auto_respond")
    else:
        outcome_ok = not _is_provider_fallback(answer) and action in (None, "auto_respond")

    result = CaseResult(
        case_id=case.case_id,
        category=case.category,
        passed=(
            contract_ok
            and outcome_ok
            and source_recall == 1.0
            and fact_coverage == 1.0
            and not violations
        ),
        source_recall=source_recall,
        required_fact_coverage=fact_coverage,
        response_contract=float(contract_ok),
        prohibited_claims=violations,
        latency_seconds=round(max(latency_seconds, 0.0), 3),
        verified_role=response.get("_verified_role"),
        cache_hit=(response.get("cache") or {}).get("hit")
        if isinstance(response.get("cache"), dict)
        else None,
        response_origin="cache"
        if isinstance(response.get("cache"), dict) and response["cache"].get("hit") is True
        else "provider_fallback"
        if _is_provider_fallback(answer)
        else "unknown",
    )
    if judge_enabled:
        result.judge = _judge(case, response)
    return result


def evaluate_cases(
    cases: list[GoldenCase],
    responder: Responder,
    *,
    judge_enabled: bool = False,
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        try:
            response, latency = responder(case)
            results.append(score_response(case, response, latency, judge_enabled=judge_enabled))
        except Exception as exc:  # noqa: BLE001 - one failed case must not abort later cases
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    category=case.category,
                    passed=False,
                    source_recall=0.0,
                    required_fact_coverage=0.0,
                    response_contract=0.0,
                    prohibited_claims=[],
                    latency_seconds=0.0,
                    error=(
                        f"{exc.__class__.__name__}: {exc}"
                        if isinstance(exc, ValueError)
                        else exc.__class__.__name__
                    ),
                )
            )
    return results


def build_report(
    suite: EvaluationSuite,
    cases: list[GoldenCase],
    results: list[CaseResult],
    *,
    mode: Literal["offline", "live"],
    provider: str | None = None,
    model: str | None = None,
    cache_mode: str = "controlled",
    target_sha: str | None = None,
    excluded_count: int = 0,
    judge_requested: bool = False,
) -> EvaluationReport:
    if len(cases) != len(results):
        raise ValueError("case and result counts must match")
    source_results = [
        result for case, result in zip(cases, results, strict=True) if case.expected_sources
    ]
    fact_results = [
        result for case, result in zip(cases, results, strict=True) if case.required_facts
    ]
    eligible = (
        [result for result in results if result.judge.status != "not_applicable"]
        if judge_requested
        else []
    )
    judged = [result for result in eligible if result.judge.status == "available"]
    metrics = EvaluationMetrics(
        case_pass_rate=_mean([float(item.passed) for item in results]),
        source_recall=_mean([item.source_recall for item in source_results]),
        required_fact_coverage=_mean([item.required_fact_coverage for item in fact_results]),
        response_contract=_mean([item.response_contract for item in results]),
        prohibited_claim_violations=sum(len(item.prohibited_claims) for item in results),
        request_errors=sum(item.error is not None for item in results),
        average_latency_seconds=_mean([item.latency_seconds for item in results]),
        ragas_evaluated=len(judged),
        ragas_eligible=len(eligible),
        ragas_faithfulness=_mean(
            [item.judge.faithfulness for item in judged if item.judge.faithfulness is not None]
        )
        if judged
        else None,
        ragas_context_recall=_mean(
            [item.judge.context_recall for item in judged if item.judge.context_recall is not None]
        )
        if any(item.judge.context_recall is not None for item in judged)
        else None,
    )
    thresholds = suite.thresholds
    passed = (
        all(item.passed for item in results)
        and (not judge_requested or bool(judged) and len(judged) == len(eligible))
        and metrics.source_recall >= thresholds.source_recall
        and metrics.required_fact_coverage >= thresholds.required_fact_coverage
        and metrics.response_contract >= thresholds.response_contract
        and metrics.prohibited_claim_violations <= thresholds.prohibited_claim_violations
        and metrics.request_errors == 0
    )
    return EvaluationReport(
        status="passed" if passed else "failed",
        mode=mode,
        evidence_scope=(
            "evaluator_contract_only" if mode == "offline" else "observed_application_response"
        ),
        generation=suite.generation,
        commit_sha=target_sha or ("offline_fixture" if mode == "offline" else "unknown"),
        provider=provider,
        model=model,
        cache_mode=cache_mode,
        excluded_count=excluded_count,
        case_count=len(results),
        metrics=metrics,
        thresholds=thresholds,
        cases=results,
    )


def offline_responder(case: GoldenCase) -> tuple[dict[str, Any], float]:
    answer = " ".join(case.required_facts) or "Policy response is grounded."
    response: dict[str, Any] = {"answer": answer, "sources": case.expected_sources}
    if case.expected_outcome == "grounded_no_answer":
        response["answer"] = (
            "KRAKEN does not have enough permitted internal evidence to answer this request."
        )
    elif case.expected_outcome == "ticket_details":
        response["answer"] = f"Ticket Information: {case.expected_sources[0]} {answer}"
        response["action_taken"] = "get_ticket_status"
        response["action_result"] = {"success": True, "ticket_id": case.expected_sources[0]}
    elif case.expected_outcome == "cache_safe_answer":
        response["cache"] = {"hit": True}
    elif case.expected_outcome == "truthful_fallback":
        response["answer"] = "The AI provider is temporarily unavailable. No action was performed."
    return response, 0.0


def target_revision(client: httpx.Client, expected_sha: str | None = None) -> str:
    """Read build identity from the target, rejecting placeholders and mismatches."""
    response = client.get("/version")
    response.raise_for_status()
    body = response.json()
    sha = body.get("commit_sha") if isinstance(body, dict) else None
    if (
        not isinstance(sha, str)
        or len(sha) != 40
        or not all(c in "0123456789abcdef" for c in sha)
        or sha == "0" * 40
    ):
        raise ValueError("target /version did not provide a verified commit SHA")
    if expected_sha and sha != expected_sha:
        raise ValueError(f"target revision {sha} does not match expected {expected_sha}")
    return sha


def establish_case_session(client: httpx.Client, role: str, generation: str) -> tuple[str, str]:
    identity_response = client.post("/v1/session")
    identity_response.raise_for_status()
    identity = identity_response.json()
    session_id = identity.get("session_id")
    csrf_token = identity.get("csrf_token")
    if not session_id or not csrf_token or identity.get("dataset_generation") != generation:
        raise ValueError("target public session identity or generation is invalid")
    transition = client.post(
        "/v1/session/persona", json={"persona": role, "csrf_token": csrf_token}
    )
    transition.raise_for_status()
    verified = client.get(f"/v1/sessions/{session_id}")
    verified.raise_for_status()
    verified_identity = verified.json()
    if (
        verified_identity.get("persona") != role
        or verified_identity.get("session_id") != session_id
    ):
        raise ValueError(f"target did not establish required role {role}")
    return session_id, csrf_token


def make_live_responder(client: httpx.Client, generation: str) -> Responder:
    def respond(case: GoldenCase) -> tuple[dict[str, Any], float]:
        session_id, csrf_token = establish_case_session(client, case.required_role, generation)
        if case.expected_outcome == "cache_safe_answer":
            warmup = client.post(
                "/v1/run",
                json={"message": case.query},
                headers={"X-CSRF-Token": csrf_token},
            )
            warmup.raise_for_status()
        started = time.perf_counter()
        response = client.post(
            "/v1/run",
            json={"message": case.query},
            headers={"X-CSRF-Token": csrf_token},
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TypeError("evaluation response must be a JSON object")
        if body.get("session_id") != session_id:
            raise ValueError("response session does not match verified identity")
        body["_verified_role"] = case.required_role
        return body, time.perf_counter() - started

    return respond


def measure_stream(
    client: httpx.Client,
    *,
    message: str,
    role: str,
    generation: str,
    disconnect_after_delta: bool = False,
) -> dict[str, Any]:
    session_id, csrf_token = establish_case_session(client, role, generation)
    started = time.perf_counter()
    first_delta_ms: float | None = None
    terminal_ms: float | None = None
    cache_hit = False
    terminal_answer: Any = None
    error: str | None = None
    disconnected = False
    with client.stream(
        "POST",
        "/v1/run/stream",
        json={"message": message},
        headers={"X-CSRF-Token": csrf_token},
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except ValueError:
                error = "malformed SSE event"
                break
            if event.get("status") == "cache_hit":
                cache_hit = True
            if event.get("status") == "error":
                error = str(event.get("message") or "stream error")
                break
            if event.get("status") == "delta" and event.get("content") and first_delta_ms is None:
                first_delta_ms = round((time.perf_counter() - started) * 1000, 1)
                if disconnect_after_delta:
                    disconnected = True
                    break
            if event.get("node") == "done" and event.get("status") == "end":
                terminal_ms = round((time.perf_counter() - started) * 1000, 1)
                terminal_response = event.get("response")
                if isinstance(terminal_response, dict):
                    terminal_answer = terminal_response.get("answer")
                break
    if not disconnected and terminal_ms is None and error is None:
        error = "stream ended without terminal event"
    if cache_hit:
        category = "cache"
    elif message.strip().casefold() in {"hi", "hello", "hey"}:
        category = "greeting"
    elif _is_provider_fallback(terminal_answer):
        category = "provider_fallback"
    elif first_delta_ms is not None:
        category = "generated"
    else:
        category = "terminal_only_unknown"
    return {
        "session_id": session_id,
        "verified_role": role,
        "category": category,
        "first_delta_ms": first_delta_ms,
        "terminal_ms": terminal_ms,
        "disconnected_after_delta": disconnected,
        "error": error,
    }


def summarize_stream_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({sample["category"] for sample in samples}):
        group = [sample for sample in samples if sample["category"] == category]
        first = sorted(
            sample["first_delta_ms"] for sample in group if sample["first_delta_ms"] is not None
        )
        terminal = sorted(
            sample["terminal_ms"] for sample in group if sample["terminal_ms"] is not None
        )
        by_category[category] = {
            "samples": len(group),
            "errors": sum(bool(sample["error"]) for sample in group),
            "first_delta_samples": len(first),
            "terminal_samples": len(terminal),
            "first_delta_median_ms": statistics.median(first) if first else None,
            "terminal_median_ms": statistics.median(terminal) if terminal else None,
            "terminal_p95_ms": terminal[min(len(terminal) - 1, int(0.95 * len(terminal)))]
            if terminal
            else None,
        }
    return by_category


def write_reports(report: EvaluationReport, json_path: Path, junit_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")

    suite = ET.Element(
        "testsuite",
        name="kraken-ai-evaluation",
        tests=str(report.case_count),
        failures=str(sum(not item.passed for item in report.cases)),
        errors=str(sum(item.error is not None for item in report.cases)),
    )
    for result in report.cases:
        case_node = ET.SubElement(
            suite,
            "testcase",
            classname=f"ai-evaluation.{result.category}",
            name=result.case_id,
            time=str(result.latency_seconds),
        )
        if not result.passed:
            failure = ET.SubElement(case_node, "failure", message=result.error or "quality gate")
            failure.text = json.dumps(
                {
                    "source_recall": result.source_recall,
                    "required_fact_coverage": result.required_fact_coverage,
                    "response_contract": result.response_contract,
                    "prohibited_claims": result.prohibited_claims,
                },
                sort_keys=True,
            )
    ET.ElementTree(suite).write(junit_path, encoding="utf-8", xml_declaration=True)


def print_report(report: EvaluationReport) -> None:
    print(
        f"AI evaluation {report.status}: mode={report.mode} cases={report.case_count} "
        f"case_pass_rate={report.metrics.case_pass_rate:.1%} "
        f"source_recall={report.metrics.source_recall:.1%} "
        f"fact_coverage={report.metrics.required_fact_coverage:.1%} "
        f"contract={report.metrics.response_contract:.1%} "
        f"violations={report.metrics.prohibited_claim_violations} "
        f"errors={report.metrics.request_errors}"
    )
    for result in report.cases:
        if not result.passed:
            print(f"  failed: {result.case_id} ({result.category}) {result.error or 'metrics'}")
    if report.metrics.ragas_eligible:
        print(
            f"RAGAS: {report.metrics.ragas_evaluated}/{report.metrics.ragas_eligible} "
            f"eligible cases, faithfulness={report.metrics.ragas_faithfulness}, "
            f"context_recall={report.metrics.ragas_context_recall}"
        )


def _judge(case: GoldenCase, response: dict[str, Any]) -> JudgeResult:
    if case.category in {"ticket_lookup", "no_answer", "provider_fallback"}:
        return JudgeResult(status="not_applicable")
    if not response.get("retrieved_chunks"):
        return JudgeResult(status="unavailable", error="MissingRetrievedChunks")
    try:
        if __package__:
            from .llm_judge import evaluate_rag_response
        else:
            from llm_judge import evaluate_rag_response

        judged = evaluate_rag_response(
            query=case.query,
            chunks=response.get("retrieved_chunks", []),
            answer=str(response.get("answer", "")),
            reference_facts=case.required_facts,
        )
        if judged.faithfulness is None:
            return JudgeResult(status="unavailable", error="MissingRetrievedChunkText")
        return JudgeResult(
            status="available",
            faithfulness=judged.faithfulness,
            context_recall=judged.context_recall,
        )
    except Exception as exc:  # noqa: BLE001 - judge evidence is explicitly optional
        return JudgeResult(status="unavailable", error=exc.__class__.__name__)


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _coverage(items: list[bool]) -> float:
    return sum(items) / len(items) if items else 1.0


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description="KRAKEN AI evaluation")
    parser.add_argument("--mode", choices=("offline", "live", "stream"), default="offline")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", ""))
    parser.add_argument("--expected-sha", help="Require an exact target /version commit SHA")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--cache-mode", default="configured")
    parser.add_argument("--ragas", "--judge", dest="judge", action="store_true")
    parser.add_argument("--case")
    parser.add_argument(
        "--samples", type=int, default=5, help="Stream measurements per selected case"
    )
    parser.add_argument("--disconnect-after-delta", action="store_true")
    parser.add_argument("--json-report", type=Path, default=Path("reports/ai-evaluation.json"))
    parser.add_argument("--junit-report", type=Path, default=Path("reports/ai-evaluation.xml"))
    args = parser.parse_args()
    if args.judge and args.mode != "live":
        parser.error("--ragas requires --mode live with observed retrieval context")

    suite, cases = load_suite()
    if args.case:
        cases = [case for case in cases if case.case_id == args.case]
        if not cases:
            parser.error(f"unknown case ID: {args.case}")
    excluded_count = 0
    if args.mode == "live":
        # Provider outages require fault injection; normal live requests cannot verify this category.
        excluded_count = sum(case.category == "provider_fallback" for case in cases)
        cases = [case for case in cases if case.category != "provider_fallback"]
        if not cases:
            parser.error("provider fallback cases require a fault-injection target")

    if args.mode in {"live", "stream"}:
        provider = None
        model = None
        with httpx.Client(
            base_url=args.base_url.rstrip("/"),
            headers={"X-API-Key": args.api_key} if args.api_key else {},
            timeout=args.timeout_seconds,
            follow_redirects=True,
        ) as client:
            try:
                target_sha = target_revision(client, args.expected_sha)
            except (httpx.HTTPError, ValueError) as exc:
                parser.error(str(exc))
            if args.mode == "stream":
                if not args.case:
                    parser.error("--case is required for stream measurements")
                if args.samples < 1:
                    parser.error("--samples must be positive")
                samples = []
                for _ in range(args.samples):
                    try:
                        samples.append(
                            measure_stream(
                                client,
                                message=cases[0].query,
                                role=cases[0].required_role,
                                generation=suite.generation,
                                disconnect_after_delta=args.disconnect_after_delta,
                            )
                        )
                    except (httpx.HTTPError, ValueError) as exc:
                        samples.append(
                            {
                                "category": "unknown",
                                "first_delta_ms": None,
                                "terminal_ms": None,
                                "error": exc.__class__.__name__,
                                "disconnected_after_delta": False,
                            }
                        )
                stream_report = {
                    "mode": "stream",
                    "evidence_scope": "observed_application_stream",
                    "commit_sha": target_sha,
                    "generation": suite.generation,
                    "case_id": cases[0].case_id,
                    "sample_count": len(samples),
                    "excluded_count": sum(bool(sample["error"]) for sample in samples),
                    "provider": None,
                    "model": None,
                    "categories": summarize_stream_samples(samples),
                    "samples": samples,
                }
                args.json_report.parent.mkdir(parents=True, exist_ok=True)
                args.json_report.write_text(
                    json.dumps(stream_report, indent=2) + "\n", encoding="utf-8"
                )
                print(
                    f"Stream measurements: {len(samples)} samples, {stream_report['excluded_count']} errors"
                )
                return 1 if stream_report["excluded_count"] else 0
            results = evaluate_cases(
                cases,
                make_live_responder(client, suite.generation),
                judge_enabled=args.judge,
            )
    else:
        provider = None
        model = None
        target_sha = None
        results = evaluate_cases(cases, offline_responder, judge_enabled=args.judge)

    report = build_report(
        suite,
        cases,
        results,
        mode=args.mode,
        provider=provider,
        model=model,
        cache_mode="controlled" if args.mode == "offline" else args.cache_mode,
        target_sha=target_sha,
        excluded_count=excluded_count,
        judge_requested=args.judge,
    )
    write_reports(report, args.json_report, args.junit_report)
    print_report(report)
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

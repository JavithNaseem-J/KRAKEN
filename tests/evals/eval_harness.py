from __future__ import annotations

import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

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
    status: Literal["disabled", "available", "unavailable"] = "disabled"
    faithfulness: float | None = None
    context_recall: float | None = None
    answer_relevance: float | None = None
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
    judge: JudgeResult = Field(default_factory=JudgeResult)


class EvaluationMetrics(BaseModel):
    source_recall: float
    required_fact_coverage: float
    response_contract: float
    prohibited_claim_violations: int
    request_errors: int
    average_latency_seconds: float


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
    case_count: int
    metrics: EvaluationMetrics
    thresholds: EvaluationThresholds
    cases: list[CaseResult]


Responder = Callable[[GoldenCase], tuple[dict[str, Any], float]]


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
    source_recall = _coverage([source.casefold() in serialized for source in case.expected_sources])
    fact_coverage = _coverage([fact.casefold() in answer_text for fact in case.required_facts])
    violations = [claim for claim in case.prohibited_claims if claim.casefold() in serialized]

    result = CaseResult(
        case_id=case.case_id,
        category=case.category,
        passed=contract_ok and source_recall == 1.0 and fact_coverage == 1.0 and not violations,
        source_recall=source_recall,
        required_fact_coverage=fact_coverage,
        response_contract=float(contract_ok),
        prohibited_claims=violations,
        latency_seconds=round(max(latency_seconds, 0.0), 3),
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
                    error=exc.__class__.__name__,
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
) -> EvaluationReport:
    if len(cases) != len(results):
        raise ValueError("case and result counts must match")
    source_results = [
        result for case, result in zip(cases, results, strict=True) if case.expected_sources
    ]
    fact_results = [
        result for case, result in zip(cases, results, strict=True) if case.required_facts
    ]
    metrics = EvaluationMetrics(
        source_recall=_mean([item.source_recall for item in source_results]),
        required_fact_coverage=_mean([item.required_fact_coverage for item in fact_results]),
        response_contract=_mean([item.response_contract for item in results]),
        prohibited_claim_violations=sum(len(item.prohibited_claims) for item in results),
        request_errors=sum(item.error is not None for item in results),
        average_latency_seconds=_mean([item.latency_seconds for item in results]),
    )
    thresholds = suite.thresholds
    passed = (
        metrics.source_recall >= thresholds.source_recall
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
        commit_sha=(os.getenv("KRAKEN_COMMIT_SHA") or os.getenv("RENDER_GIT_COMMIT") or "unknown"),
        provider=provider,
        model=model,
        cache_mode=cache_mode,
        case_count=len(results),
        metrics=metrics,
        thresholds=thresholds,
        cases=results,
    )


def offline_responder(case: GoldenCase) -> tuple[dict[str, Any], float]:
    answer = " ".join(case.required_facts) or "Synthetic policy response is grounded."
    return {"answer": answer, "sources": case.expected_sources}, 0.0


def make_live_responder(client: httpx.Client) -> Responder:
    def respond(case: GoldenCase) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        response = client.post(
            "/v1/run",
            json={
                "message": case.query,
                "session_id": f"eval-{case.case_id.lower()}",
                "user_id": "evaluation-runner",
                "metadata": {"operator_role": case.required_role},
            },
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TypeError("evaluation response must be a JSON object")
        return body, time.perf_counter() - started

    return respond


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
        f"source_recall={report.metrics.source_recall:.1%} "
        f"fact_coverage={report.metrics.required_fact_coverage:.1%} "
        f"contract={report.metrics.response_contract:.1%} "
        f"violations={report.metrics.prohibited_claim_violations} "
        f"errors={report.metrics.request_errors}"
    )
    for result in report.cases:
        if not result.passed:
            print(f"  failed: {result.case_id} ({result.category}) {result.error or 'metrics'}")


def _judge(case: GoldenCase, response: dict[str, Any]) -> JudgeResult:
    try:
        from tests.evals.llm_judge import evaluate_rag_response

        judged = evaluate_rag_response(
            query=case.query,
            chunks=response.get("retrieved_chunks", []),
            answer=str(response.get("answer", "")),
        )
        return JudgeResult(
            status="available",
            faithfulness=judged.faithfulness,
            context_recall=judged.context_recall,
            answer_relevance=judged.answer_relevance,
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


def _provider_label(base_url: str) -> str:
    return urlparse(base_url).hostname or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="KRAKEN deterministic AI evaluation")
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY", ""))
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--cache-mode", default="configured")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--json-report", type=Path, default=Path("reports/ai-evaluation.json"))
    parser.add_argument("--junit-report", type=Path, default=Path("reports/ai-evaluation.xml"))
    args = parser.parse_args()

    suite, cases = load_suite()
    if args.case:
        cases = [case for case in cases if case.case_id == args.case]
        if not cases:
            parser.error(f"unknown case ID: {args.case}")

    if args.mode == "live":
        if not args.api_key:
            parser.error("--api-key or EVAL_API_KEY is required in live mode")
        provider_url = os.getenv("LLM_BASE_URL", "")
        provider = _provider_label(provider_url) if provider_url else "configured-by-target"
        model = os.getenv("LLM_MODEL", "configured-by-target")
        with httpx.Client(
            base_url=args.base_url.rstrip("/"),
            headers={"X-API-Key": args.api_key},
            timeout=args.timeout_seconds,
            follow_redirects=True,
        ) as client:
            results = evaluate_cases(
                cases,
                make_live_responder(client),
                judge_enabled=args.judge,
            )
    else:
        provider = None
        model = None
        results = evaluate_cases(cases, offline_responder, judge_enabled=args.judge)

    report = build_report(
        suite,
        cases,
        results,
        mode=args.mode,
        provider=provider,
        model=model,
        cache_mode="controlled" if args.mode == "offline" else args.cache_mode,
    )
    write_reports(report, args.json_report, args.junit_report)
    print_report(report)
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

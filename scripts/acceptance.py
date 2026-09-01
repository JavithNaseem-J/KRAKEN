from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx


class AcceptanceError(RuntimeError):
    pass


SCENARIOS_PATH = Path(__file__).parent.parent / "data/synthetic/capability_scenarios.json"


def load_scenarios() -> dict[str, dict[str, Any]]:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    selected: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        selected.setdefault(str(scenario["capability"]), scenario)
    return selected


def contains_key(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(contains_key(item, target) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, target) for item in value)
    return False


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def run(base_url: str, timeout_seconds: float = 240.0) -> tuple[list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []
    scenarios = load_scenarios()
    with httpx.Client(
        base_url=base_url.rstrip("/"), timeout=timeout_seconds, follow_redirects=True
    ) as client:
        session_response = client.post("/v1/session")
        session_response.raise_for_status()
        session = session_response.json()
        headers = {"X-CSRF-Token": session["csrf_token"]}

        def query(message: str) -> dict[str, Any]:
            response = client.post(
                "/v1/run",
                json={"message": message, "session_id": session["session_id"]},
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            require(not contains_key(result, "reasoning"), "response exposed model reasoning")
            return result

        def record(name: str, check: Any) -> Any:
            try:
                result = check()
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}: {exc}")
                return None
            passed.append(name)
            return result

        record(
            "knowledge_rag",
            lambda: _check_rag(
                query(scenarios["knowledge_rag"]["query"]), scenarios["knowledge_rag"]
            ),
        )

        cache_query = scenarios["semantic_cache"]["query"]
        query(cache_query)
        record("semantic_cache", lambda: _check_semantic_cache(query(cache_query)))

        record(
            "ticket_lookup",
            lambda: require(
                all(
                    source in json.dumps(query(scenarios["ticket_lookup"]["query"]))
                    for source in scenarios["ticket_lookup"]["expected_sources"]
                ),
                "ticket details missing",
            ),
        )

        record(
            "create_ticket",
            lambda: _check_create_ticket(query(scenarios["safe_create_ticket"]["query"])),
        )

        pending_holder: dict[str, Any] = {}

        def hitl_interception() -> None:
            initiator = client.post(
                "/v1/session/persona",
                json={"persona": "tier1_analyst", "csrf_token": session["csrf_token"]},
            )
            initiator.raise_for_status()
            pending = query(scenarios["critical_hitl"]["query"])
            require(pending.get("status") == "pending_approval", "critical action did not pause")
            pending_holder.update(pending)

        record("hitl_interception", hitl_interception)

        def hitl_resumption() -> None:
            require(bool(pending_holder.get("approval_id")), "no pending approval to resume")
            persona = client.post(
                "/v1/session/persona",
                json={"persona": "incident_commander", "csrf_token": session["csrf_token"]},
            )
            persona.raise_for_status()
            details = client.get(f"/approve/{pending_holder['approval_id']}/details")
            details.raise_for_status()
            decision = client.post(
                f"/approve/{pending_holder['approval_id']}/decision",
                data={
                    "decision": "approve",
                    "csrf_token": details.json()["csrf_token"],
                    "session_csrf_token": session["csrf_token"],
                },
                headers={"Accept": "application/json"},
            )
            decision.raise_for_status()
            require(decision.json().get("agent_response"), "HITL graph did not resume")
            require(
                '"synthetic": true' in json.dumps(decision.json()).lower(),
                "HITL result lacked synthetic action evidence",
            )

        record("hitl_resumption", hitl_resumption)

        def prompt_injection() -> None:
            injection = client.post(
                "/v1/run",
                json={
                    "message": scenarios["prompt_injection_user"]["query"],
                    "session_id": "x",
                },
                headers=headers,
            )
            require(injection.status_code == 400, "prompt injection was not rejected")

        record("prompt_injection_defense", prompt_injection)

        def sse_lifecycle() -> None:
            stream = client.stream(
                "POST",
                "/v1/run/stream",
                json={"message": scenarios["sse"]["query"], "session_id": "x"},
                headers=headers,
            )
            with stream as response:
                response.raise_for_status()
                events = [
                    json.loads(line[6:])
                    for line in response.iter_lines()
                    if line.startswith("data: ")
                ]
            require(bool(events) and events[-1].get("node") == "done", "SSE terminal event missing")
            require(
                sum("response" in event for event in events) == 1,
                "SSE emitted multiple terminals",
            )

        record("sse_lifecycle", sse_lifecycle)
    return passed, failed


def _check_rag(rag: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    require(bool(rag.get("answer")), "RAG returned no answer")
    require(bool(rag.get("sources")), "RAG returned no grounded sources")
    require(
        "provider is temporarily unavailable" not in rag["answer"].lower(),
        "false RAG success",
    )
    serialized = json.dumps(rag).lower()
    for fact in scenario.get("required_facts", []):
        require(str(fact).lower() in serialized, f"RAG missing required fact: {fact}")
    for source in scenario.get("expected_sources", []):
        require(str(source).lower() in serialized, f"RAG missing expected source: {source}")
    return rag


def _check_semantic_cache(cached: dict[str, Any]) -> None:
    require(cached.get("cache", {}).get("hit") is True, "semantic cache did not accelerate")
    require(
        "provider is temporarily unavailable" not in str(cached.get("answer", "")).lower(),
        "semantic cache returned provider fallback",
    )


def _check_create_ticket(created: dict[str, Any]) -> None:
    require(created.get("action_taken") == "create_ticket", "ticket was not created immediately")
    result = json.dumps(created.get("action_result"))
    require("SYN-" in result, "synthetic ticket ID missing")
    require('"synthetic": true' in result.lower(), "synthetic action evidence missing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    args = parser.parse_args()
    try:
        passed, failed = run(args.base_url, timeout_seconds=args.timeout_seconds)
    except (AcceptanceError, httpx.HTTPError) as exc:
        print(f"acceptance failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"acceptance passed: {len(passed)}/8 ({', '.join(passed)})")
    if failed:
        for failure in failed:
            print("acceptance failed: " + failure, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

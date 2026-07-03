"""
Evaluation harness — runs the golden dataset against the live system.

Usage:
    # Start the system first: make up && make ingest
    python tests/evals/eval_harness.py [--base-url http://localhost:8000] [--api-key your-key]

Scoring:
  keyword_score    — fraction of expected_keywords found in the answer (case-insensitive)
  action_match     — 1.0 if selected_action matches expected, 0.0 otherwise
  hitl_match       — 1.0 if HITL status matches expected_hitl
  source_coverage  — fraction of expected_sources found in actual sources

Overall score per case = mean(keyword_score, action_match, hitl_match, source_coverage)
Pass threshold = 0.7 (configurable via --threshold)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"


# ── Scoring functions ─────────────────────────────────────────────────────────

def keyword_score(answer: str, keywords: list[str]) -> float:
    """Fraction of expected keywords found in the answer (case-insensitive partial match)."""
    if not keywords:
        return 1.0
    answer_lower = answer.lower()
    matches = sum(
        1 for kw in keywords
        if kw.lower() in answer_lower
    )
    return matches / len(keywords)


def action_match(actual: str | None, expected: str) -> float:
    return 1.0 if actual == expected else 0.0


def hitl_match(response_body: dict, expected_hitl: bool) -> float:
    """
    Check if HITL was triggered correctly.
    pending_approval in response → HITL fired.
    final_answer in response → no HITL.
    """
    is_pending = response_body.get("status") == "pending_approval"
    return 1.0 if (is_pending == expected_hitl) else 0.0


def source_coverage(actual_sources: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    actual_set = {s.lower() for s in actual_sources}
    return sum(1 for s in expected if s.lower() in actual_set) / len(expected)


# ── Runner ────────────────────────────────────────────────────────────────────

def run_case(
    case: dict,
    base_url: str,
    api_key: str,
    session_id: str,
) -> dict:
    """Run a single eval case and return a result dict."""
    start = time.perf_counter()

    try:
        with httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=60.0,
        ) as client:
            resp = client.post(
                "/v1/run",
                json={
                    "message":    case["question"],
                    "session_id": session_id,
                    "user_id":    "eval_harness",
                },
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        return {
            "id":      case["id"],
            "score":   0.0,
            "error":   str(exc),
            "latency": time.perf_counter() - start,
        }

    latency = time.perf_counter() - start

    # Extract fields
    answer          = body.get("answer", "")
    actual_action   = body.get("action_taken")
    actual_sources  = body.get("sources", [])

    # Score
    kw_score  = keyword_score(answer, case.get("expected_keywords", []))
    act_score = action_match(actual_action, case.get("expected_action", "respond_only"))
    hl_score  = hitl_match(body, case.get("expected_hitl", False))
    src_score = source_coverage(actual_sources, case.get("expected_sources", []))
    overall   = (kw_score + act_score + hl_score + src_score) / 4.0

    return {
        "id":             case["id"],
        "category":       case.get("category"),
        "question":       case["question"][:60] + "...",
        "score":          round(overall, 3),
        "keyword_score":  round(kw_score, 3),
        "action_match":   round(act_score, 3),
        "hitl_match":     round(hl_score, 3),
        "source_coverage": round(src_score, 3),
        "actual_action":  actual_action,
        "latency_s":      round(latency, 2),
    }


def print_report(results: list[dict], threshold: float) -> int:
    """Print evaluation report. Returns exit code (0=pass, 1=fail)."""
    print()
    print("=" * 72)
    print("  AKEA Evaluation Report")
    print("=" * 72)
    print(f"  Cases: {len(results)}   Threshold: {threshold:.0%}")
    print()

    passed = 0
    for r in results:
        status = "✅ PASS" if r["score"] >= threshold else "❌ FAIL"
        if r.get("error"):
            status = "💥 ERROR"
        if r["score"] >= threshold:
            passed += 1
        print(f"  {status}  [{r['id']}] {r.get('category', '')}")
        print(f"         Q: {r['question']}")
        if r.get("error"):
            print(f"         Error: {r['error']}")
        else:
            print(
                f"         Score: {r['score']:.0%}  "
                f"(kw={r['keyword_score']:.0%}, "
                f"act={r['action_match']:.0%}, "
                f"hitl={r['hitl_match']:.0%}, "
                f"src={r['source_coverage']:.0%})  "
                f"{r['latency_s']}s"
            )
        print()

    overall_avg = sum(r["score"] for r in results) / len(results) if results else 0
    print("─" * 72)
    print(f"  Overall average: {overall_avg:.1%}   Passed: {passed}/{len(results)}")
    print("=" * 72)
    print()

    return 0 if passed == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="AKEA Evaluation Harness")
    parser.add_argument("--base-url",  default="http://localhost:8000")
    parser.add_argument("--api-key",   default="dev-key-1:developer")
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--case",      help="Run only this case ID")
    args = parser.parse_args()

    cases = json.loads(GOLDEN_PATH.read_text())
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"Case '{args.case}' not found.")
            sys.exit(1)

    print(f"\nRunning {len(cases)} eval cases against {args.base_url} ...")

    results = []
    for i, case in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] {case['id']}  {case['question'][:50]}...")
        result = run_case(
            case=case,
            base_url=args.base_url,
            api_key=args.api_key.split(":")[0],   # Use key part only
            session_id=f"eval-{case['id']}",
        )
        results.append(result)

    exit_code = print_report(results, args.threshold)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

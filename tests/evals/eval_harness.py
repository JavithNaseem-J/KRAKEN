"""
Evaluation harness — runs the golden dataset against the live system and scores
responses using an LLM-as-a-Judge (Faithfulness, Context Recall, Answer Relevance).

Usage:
    # Start the system first: make up && make ingest
    python tests/evals/eval_harness.py [--base-url http://localhost:8000] [--api-key your-key]

Scoring:
  Each case is scored on three axes by the LLM judge:
    faithfulness       — 0.0-1.0: answer stays within retrieved chunks
    context_recall     — 0.0-1.0: relevant facts reflected in answer
    answer_relevance   — 0.0-1.0: answer addresses the query directly
  Overall score per case = mean(faithfulness, context_recall, answer_relevance)
  Pass threshold = 0.5 (configurable via --threshold)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"


# ── Runner ────────────────────────────────────────────────────────────────────


def run_case(
    case: dict,
    base_url: str,
    api_key: str,
    session_id: str,
) -> dict:
    """Run a single eval case, get the response, and score it with the LLM judge."""
    start = time.perf_counter()

    # 1. Query the system
    try:
        with httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=60.0,
        ) as client:
            resp = client.post(
                "/v1/run",
                json={
                    "message": case["question"],
                    "session_id": session_id,
                    "user_id": "eval_harness",
                },
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        return {
            "id": case["id"],
            "category": case.get("category"),
            "score": 0.0,
            "error": str(exc),
            "latency_s": 0.0,
        }

    latency = time.perf_counter() - start

    # 2. Score with LLM judge
    try:
        from tests.evals.llm_judge import evaluate_rag_response

        chunks = body.get("retrieved_chunks", [])
        answer = body.get("answer", "")
        eval_result = evaluate_rag_response(
            query=case["question"],
            chunks=chunks,
            answer=answer,
        )
        overall = round(
            (eval_result.faithfulness + eval_result.context_recall + eval_result.answer_relevance) / 3.0,
            3,
        )
    except Exception:
        overall = 0.0
        eval_result = None
        answer = body.get("answer", "")
        chunks = []

    return {
        "id": case["id"],
        "category": case.get("category"),
        "question": case["question"][:60] + "...",
        "answer_preview": str(answer)[:80],
        "score": overall,
        "faithfulness": round(eval_result.faithfulness, 3) if eval_result else 0.0,
        "context_recall": round(eval_result.context_recall, 3) if eval_result else 0.0,
        "answer_relevance": round(eval_result.answer_relevance, 3) if eval_result else 0.0,
        "num_chunks": len(chunks),
        "latency_s": round(latency, 2),
    }


def print_report(results: list[dict], threshold: float) -> int:
    """Print evaluation report. Returns exit code (0=pass, 1=fail)."""
    print()
    print("=" * 72)
    print("  KRAKEN LLM-as-a-Judge Evaluation Report")
    print("=" * 72)
    print(f"  Cases: {len(results)}   Threshold: {threshold:.1%}")
    print()

    passed = 0
    for r in results:
        if r.get("error"):
            status = "💥 ERROR"
        elif r["score"] >= threshold:
            status = "✅ PASS"
            passed += 1
        else:
            status = "❌ FAIL"

        print(f"  {status}  [{r['id']}] {r.get('category', '')}")
        print(f"         Q: {r['question']}")
        if r.get("error"):
            print(f"         Error: {r['error']}")
        else:
            print(
                f"         Score: {r['score']:.0%}  "
                f"(faith={r['faithfulness']:.0%}, "
                f"recall={r['context_recall']:.0%}, "
                f"rel={r['answer_relevance']:.0%})  "
                f"{r['latency_s']}s  [{r['num_chunks']} chunks]"
            )
        print()

    overall_avg = sum(r["score"] for r in results) / len(results) if results else 0
    avg_faith = sum(r.get("faithfulness", 0) for r in results) / len(results) if results else 0
    avg_recall = sum(r.get("context_recall", 0) for r in results) / len(results) if results else 0
    avg_rel = sum(r.get("answer_relevance", 0) for r in results) / len(results) if results else 0
    avg_latency = (
        sum(r["latency_s"] for r in results if "latency_s" in r) / len(results) if results else 0
    )

    print("─" * 72)
    print("  Summary Metrics:")
    print(f"  • Faithfulness:           {avg_faith:.1%}")
    print(f"  • Context Recall:         {avg_recall:.1%}")
    print(f"  • Answer Relevance:       {avg_rel:.1%}")
    print(f"  • Average Latency:        {avg_latency:.2f}s")
    print(f"  • Overall Composite:      {overall_avg:.1%}   Passed: {passed}/{len(results)}")
    print("=" * 72)
    print()

    return 0 if passed == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="KRAKEN LLM-as-a-Judge Eval Harness")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default="dev-key-alice-longer-secure-key:alice")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--case", help="Run only this case ID")
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
            api_key=args.api_key.split(":")[0],
            session_id=f"eval-{case['id']}",
        )
        results.append(result)

    # Write JSON report
    report_path = Path(__file__).parent / "eval_report.json"
    report_path.write_text(json.dumps(results, indent=2))
    print(f"  Report written to {report_path}")

    exit_code = print_report(results, args.threshold)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

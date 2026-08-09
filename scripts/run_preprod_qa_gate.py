"""
Master Enterprise Pre-Production QA Gate Pipeline.

Executes all 4 Pre-Production Quality Gates sequentially:
1. Operational Health Check (check_health.py)
2. Unit Test Suite (pytest tests/unit)
3. RAG Precision & Faithfulness Evals (pytest tests/evals)
4. SAST & Security Audit (run_security_audit.py)
5. Concurrency Load Benchmark (test_load_concurrency.py)

Outputs a unified pass/fail enterprise QA report and sets process exit code.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_EXE = sys.executable


def run_command_step(name: str, cmd: list[str]) -> bool:
    """Execute a single testing step and print status."""
    print(f"\n========================================================")
    print(f"  EXECUTING QA GATE: {name}")
    print(f"========================================================")
    start = time.perf_counter()

    res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=False)
    elapsed = time.perf_counter() - start

    if res.returncode == 0:
        print(f"[PASS] {name} completed successfully in {elapsed:.2f}s")
        return True
    else:
        print(f"[FAIL] {name} failed with exit code {res.returncode}")
        return False


def main() -> int:
    print(f"\n" + "=" * 64)
    print(f"   AKEA FORTUNE 500 ENTERPRISE PRE-PRODUCTION QA GATEWAY")
    print(f"=" * 64)

    steps = [
        ("1. Multi-Service Operational Health Check", [PYTHON_EXE, "scripts/check_health.py"]),
        ("2. System Unit Test Suite (173 Tests)", [PYTHON_EXE, "-m", "pytest", "tests/unit"]),
        ("3. RAG Precision & Faithfulness Eval Suite", [PYTHON_EXE, "-m", "pytest", "tests/evals/test_rag_evals.py"]),
        ("4. SAST & Security Audit", [PYTHON_EXE, "scripts/run_security_audit.py"]),
        ("5. Concurrency Load Benchmark", [PYTHON_EXE, "scripts/test_load_concurrency.py"]),
    ]

    failed_steps: list[str] = []

    for name, cmd in steps:
        success = run_command_step(name, cmd)
        if not success:
            failed_steps.append(name)

    print(f"\n" + "=" * 64)
    print(f"   FINAL ENTERPRISE PRE-PRODUCTION QA GATE SUMMARY")
    print(f"=" * 64)

    if not failed_steps:
        print(f"  RESULT: ALL 5 PRE-PRODUCTION QA GATES PASSED 100% [PASS]")
        print(f"  SYSTEM IS READY FOR 100% CLOUD PRODUCTION DEPLOYMENT!")
        print(f"=" * 64 + "\n")
        return 0
    else:
        print(f"  RESULT: {len(failed_steps)} GATES FAILED [FAIL]")
        for f_name in failed_steps:
            print(f"    - {f_name}")
        print(f"=" * 64 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

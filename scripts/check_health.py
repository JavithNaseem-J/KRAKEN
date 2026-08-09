from __future__ import annotations

import os
import sys

import httpx

SERVICES = [
    ("Gateway", os.getenv("GATEWAY_URL", "http://localhost:8000")),
    ("Orchestrator", os.getenv("ORCHESTRATOR_URL", "http://localhost:8001")),
    ("Knowledge", os.getenv("KNOWLEDGE_URL", "http://localhost:8002")),
    ("Action", os.getenv("ACTION_URL", "http://localhost:8003")),
    ("Approval", os.getenv("APPROVAL_URL", "http://localhost:8004")),
    ("Memory", os.getenv("MEMORY_URL", "http://localhost:8005")),
    ("Audit", os.getenv("AUDIT_URL", "http://localhost:8006")),
]


def check_all_services() -> bool:
    print("\n========================================================")
    print("  AKEA Multi-Service Operational Health Check")
    print("========================================================")
    print(f"{'Service':<15} {'URL':<35} {'Status':<10} {'Details'}")
    print("-" * 75)

    all_healthy = True

    with httpx.Client(timeout=3.0) as client:
        for name, base_url in SERVICES:
            health_url = f"{base_url.rstrip('/')}/health"
            try:
                resp = client.get(health_url)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        status_str = data.get("status", "ok")
                        details = f"HTTP 200 — status={status_str}"
                        flag = "[OK]"
                    except Exception:
                        flag = "[OK]"
                        details = "HTTP 200"
                else:
                    flag = "[WARN]"
                    details = f"HTTP {resp.status_code}"
                    all_healthy = False
            except Exception as exc:
                flag = "[DOWN]"
                details = f"Connection failed ({type(exc).__name__})"
                all_healthy = False

            print(f"{name:<15} {health_url:<35} {flag:<10} {details}")

    print("=" * 75)
    if all_healthy:
        print("  RESULT: All services operational. [PASS]\n")
    else:
        print("  RESULT: One or more services degraded/offline.\n")

    return all_healthy


if __name__ == "__main__":
    success = check_all_services()
    sys.exit(0 if success else 1)

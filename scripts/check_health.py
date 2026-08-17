from __future__ import annotations

import os
import sys

import httpx

APP_URL = os.getenv("GATEWAY_URL", os.getenv("APP_URL", "http://localhost:8000"))


def check_health() -> bool:
    print("\n========================================================")
    print("  KRAKEN Consolidated Operational Health Check")
    print("========================================================")
    base_url = APP_URL.rstrip("/")
    print(f"  Target: {base_url}")
    print("-" * 56)

    all_healthy = True

    with httpx.Client(timeout=5.0) as client:
        # Check /health
        try:
            resp = client.get(f"{base_url}/health")
            if resp.status_code == 200:
                print(f"  /health : [OK]  HTTP 200 — {resp.json()}")
            else:
                print(f"  /health : [WARN] HTTP {resp.status_code}")
                all_healthy = False
        except Exception as exc:
            print(f"  /health : [DOWN] {type(exc).__name__}: {exc}")
            all_healthy = False

        # Check /ready
        try:
            resp = client.get(f"{base_url}/ready")
            if resp.status_code == 200:
                print(f"  /ready  : [OK]  HTTP 200 — {resp.json()}")
            else:
                print(f"  /ready  : [WARN] HTTP {resp.status_code} — {resp.text}")
                all_healthy = False
        except Exception as exc:
            print(f"  /ready  : [DOWN] {type(exc).__name__}: {exc}")
            all_healthy = False

    print("=" * 56)
    if all_healthy:
        print("  RESULT: Application operational. [PASS]\n")
    else:
        print("  RESULT: Application degraded or offline. [FAIL]\n")

    return all_healthy


if __name__ == "__main__":
    success = check_health()
    sys.exit(0 if success else 1)

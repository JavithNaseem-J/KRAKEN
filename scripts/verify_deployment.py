from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class HttpResponse(Protocol):
    status: int

    def __enter__(self) -> HttpResponse: ...

    def __exit__(self, *args: object) -> None: ...

    def read(self) -> bytes: ...


OpenUrl = Callable[..., HttpResponse]


def verify_deployment(
    base_url: str,
    expected_sha: str,
    *,
    timeout_seconds: float = 1200.0,
    initial_delay_seconds: float = 2.0,
    max_delay_seconds: float = 15.0,
    opener: OpenUrl = urlopen,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    base_url = _validate_base_url(base_url)
    expected_sha = expected_sha.strip().lower()
    if not FULL_SHA.fullmatch(expected_sha):
        raise ValueError("expected_sha must be a full 40-character lowercase Git SHA")
    if timeout_seconds < 0 or initial_delay_seconds <= 0 or max_delay_seconds <= 0:
        raise ValueError("polling durations must be positive")

    started = monotonic()
    attempts = 0
    delay = min(initial_delay_seconds, max_delay_seconds)
    last_endpoints: dict[str, dict[str, Any]] = {}

    while True:
        attempts += 1
        last_endpoints = _probe(base_url, expected_sha, opener)
        elapsed = monotonic() - started
        if all(result["ok"] for result in last_endpoints.values()):
            return _report(
                status="passed",
                base_url=base_url,
                expected_sha=expected_sha,
                attempts=attempts,
                elapsed=elapsed,
                endpoints=last_endpoints,
            )
        if elapsed >= timeout_seconds:
            return _report(
                status="failed",
                base_url=base_url,
                expected_sha=expected_sha,
                attempts=attempts,
                elapsed=elapsed,
                endpoints=last_endpoints,
            )
        sleep(min(delay, max(0.0, timeout_seconds - elapsed)))
        delay = min(delay * 1.5, max_delay_seconds)


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _probe(base_url: str, expected_sha: str, opener: OpenUrl) -> dict[str, dict[str, Any]]:
    health = _request_json(base_url, "/health", opener)
    health["ok"] = health.get("status_code") == 200 and health.get("status") == "ok"

    ready = _request_json(base_url, "/ready", opener)
    ready["ok"] = ready.get("status_code") == 200 and ready.get("status") == "ready"

    version = _request_json(base_url, "/version", opener)
    observed_sha = version.get("commit_sha")
    version["ok"] = version.get("status_code") == 200 and observed_sha == expected_sha
    version["sha_matches"] = observed_sha == expected_sha

    return {"health": health, "ready": ready, "version": version}


def _request_json(base_url: str, path: str, opener: OpenUrl) -> dict[str, Any]:
    request = Request(f"{base_url}{path}", headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=15.0) as response:
            body = json.loads(response.read().decode("utf-8"))
            result: dict[str, Any] = {"status_code": response.status}
            if path in {"/health", "/ready"}:
                result["status"] = body.get("status")
            elif path == "/version":
                result["commit_sha"] = body.get("commit_sha")
            return result
    except HTTPError as exc:
        return {"status_code": exc.code, "error": "http_error"}
    except OSError:
        return {"status_code": None, "error": "connection_error"}
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
        return {"status_code": None, "error": "invalid_response"}


def _validate_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain credentials, query parameters, or fragments")
    return normalized


def _report(
    *,
    status: str,
    base_url: str,
    expected_sha: str,
    attempts: int,
    elapsed: float,
    endpoints: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": status,
        "base_url": base_url,
        "expected_sha": expected_sha,
        "observed_sha": endpoints.get("version", {}).get("commit_sha"),
        "attempts": attempts,
        "elapsed_seconds": round(elapsed, 3),
        "endpoints": endpoints,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a deployed KRAKEN commit")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--initial-delay-seconds", type=float, default=2.0)
    parser.add_argument("--max-delay-seconds", type=float, default=15.0)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/deployment-verification.json"),
    )
    args = parser.parse_args()

    try:
        report = verify_deployment(
            args.base_url,
            args.expected_sha,
            timeout_seconds=args.timeout_seconds,
            initial_delay_seconds=args.initial_delay_seconds,
            max_delay_seconds=args.max_delay_seconds,
        )
    except ValueError as exc:
        parser.error(str(exc))

    write_report(report, args.report)
    print(
        f"deployment verification {report['status']}: "
        f"expected={report['expected_sha']} observed={report['observed_sha']} "
        f"attempts={report['attempts']}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())

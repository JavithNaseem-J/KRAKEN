"""
Comprehensive Load & Latency Benchmark Script for AKEA.

Simulates concurrent async worker tasks hitting the API Gateway, measuring P50, P90, P95, P99
latency distribution, throughput (RPS), and status code breakdown.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from typing import Any

import httpx

SAMPLE_QUERIES = [
    "How do I reset my VPN password?",
    "Escalate ticket T-1002 due to critical server downtime.",
    "What is the SLA response time for P1 incidents?",
    "Request additional logs for ticket T-1005.",
    "What are the network access guidelines for contractors?",
    "How do I resolve GlobalProtect VPN Error 51?",
    "Can I install third-party developer tools on corporate MacBooks?",
]


async def send_request(
    client: httpx.AsyncClient,
    endpoint: str,
    query: str,
    session_id: str,
) -> tuple[float, bool, int]:
    start = time.perf_counter()
    try:
        resp = await client.post(
            endpoint,
            json={
                "message": query,
                "session_id": session_id,
                "user_id": "benchmark_user",
            },
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
        success = resp.status_code == 200
        return latency_ms, success, resp.status_code
    except Exception:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return latency_ms, False, 500


async def run_benchmark(
    base_url: str,
    endpoint: str,
    api_key: str,
    total_requests: int,
    concurrency: int,
) -> dict[str, Any]:
    print("\n" + "=" * 60)
    print("  AKEA API Gateway Benchmark")
    print("=" * 60)
    print(f"  Target URL:   {base_url}{endpoint}")
    print(f"  Requests:     {total_requests}")
    print(f"  Concurrency:  {concurrency}")
    print("=" * 60 + "\n")

    limits = httpx.Limits(max_keepalive_connections=concurrency, max_connections=concurrency * 2)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    semaphore = asyncio.Semaphore(concurrency)
    results: list[tuple[float, bool, int]] = []

    async with httpx.AsyncClient(
        base_url=base_url, headers=headers, limits=limits, timeout=60.0
    ) as client:

        async def worker(idx: int) -> None:
            async with semaphore:
                query = SAMPLE_QUERIES[idx % len(SAMPLE_QUERIES)]
                session_id = f"bench-sess-{idx}"
                res = await send_request(client, endpoint, query, session_id)
                results.append(res)

        wall_start = time.perf_counter()
        tasks = [worker(i) for i in range(total_requests)]
        await asyncio.gather(*tasks)
        total_time = time.perf_counter() - wall_start

    latencies_ms = [r[0] for r in results]
    status_counts: dict[int, int] = {}
    for r in results:
        code = r[2]
        status_counts[code] = status_counts.get(code, 0) + 1

    successful_count = sum(1 for r in results if r[1])
    rps = total_requests / total_time if total_time > 0 else 0

    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)
    p50 = sorted_lat[int(n * 0.50)] if n else 0.0
    p90 = sorted_lat[int(n * 0.90)] if n >= 10 else (sorted_lat[-1] if n else 0.0)
    p95 = sorted_lat[int(n * 0.95)] if n >= 20 else (sorted_lat[-1] if n else 0.0)
    p99 = sorted_lat[int(n * 0.99)] if n >= 100 else (sorted_lat[-1] if n else 0.0)

    print("📊 BENCHMARK RESULTS")
    print("─" * 40)
    print(f"  Total Wall Time:  {total_time:.2f} s")
    print(f"  Throughput (RPS): {rps:.2f} req/sec")
    print(
        f"  Success Rate:     {successful_count}/{total_requests} ({successful_count / total_requests:.1%})"
    )
    print(f"  Status Codes:     {status_counts}")
    print()
    print("⏱️ LATENCY METRICS (ms)")
    print("─" * 40)
    print(f"  Min:  {min(latencies_ms):.2f} ms")
    print(f"  Mean: {statistics.mean(latencies_ms):.2f} ms")
    print(f"  p50:  {p50:.2f} ms")
    print(f"  p90:  {p90:.2f} ms")
    print(f"  p95:  {p95:.2f} ms")
    print(f"  p99:  {p99:.2f} ms")
    print(f"  Max:  {max(latencies_ms):.2f} ms")
    print("=" * 60 + "\n")

    return {
        "total_requests": total_requests,
        "total_time_sec": total_time,
        "rps": rps,
        "status_counts": status_counts,
        "avg_ms": statistics.mean(latencies_ms) if latencies_ms else 0.0,
        "p50_ms": p50,
        "p90_ms": p90,
        "p95_ms": p95,
        "p99_ms": p99,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AKEA Load Benchmark")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--endpoint", default="/v1/run")
    parser.add_argument("--api-key", default="dev-key-analyst-default")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    asyncio.run(
        run_benchmark(args.base_url, args.endpoint, args.api_key, args.requests, args.concurrency)
    )


if __name__ == "__main__":
    main()

"""
Single-container process manager for KRAKEN.
Launches all 7 microservices in background asyncio subprocesses inside a single container
so the entire stack can be deployed on Render's 100% Free Tier (1 Web Service).

Service Port Mapping:
  8001 - Orchestrator
  8002 - Knowledge
  8003 - Action
  8004 - Approval
  8005 - Memory
  8006 - Audit
  $PORT (default 8000) - Gateway (Public facing)
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure localhost URLs are permitted for internal intra-container communication
os.environ["ORCHESTRATOR_URL"] = os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:8001")
os.environ["KNOWLEDGE_URL"] = os.getenv("KNOWLEDGE_URL", "http://127.0.0.1:8002")
os.environ["ACTION_URL"] = os.getenv("ACTION_URL", "http://127.0.0.1:8003")
os.environ["APPROVAL_URL"] = os.getenv("APPROVAL_URL", "http://127.0.0.1:8004")
os.environ["MEMORY_URL"] = os.getenv("MEMORY_URL", "http://127.0.0.1:8005")
os.environ["AUDIT_URL"] = os.getenv("AUDIT_URL", "http://127.0.0.1:8006")
os.environ["APPROVAL_BASE_URL"] = os.getenv("APPROVAL_BASE_URL", "http://127.0.0.1:8004")
os.environ["HITL_SERVICE_TOKEN"] = os.getenv("HITL_SERVICE_TOKEN", "4f8a9c3e2b1d0e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f")

# Set single-container environment flag
os.environ["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "dev")

SERVICES = [
    ("audit", ["uvicorn", "services.audit.main:app", "--host", "127.0.0.1", "--port", "8006"]),
    ("memory", ["uvicorn", "services.memory.main:app", "--host", "127.0.0.1", "--port", "8005"]),
    ("approval", ["uvicorn", "services.approval.main:app", "--host", "127.0.0.1", "--port", "8004"]),
    ("action", ["uvicorn", "services.action.main:app", "--host", "127.0.0.1", "--port", "8003"]),
    ("knowledge", ["uvicorn", "services.knowledge.main:app", "--host", "127.0.0.1", "--port", "8002"]),
    ("orchestrator", ["uvicorn", "services.orchestrator.main:app", "--host", "127.0.0.1", "--port", "8001"]),
]


async def run_process(name: str, cmd: list[str]) -> asyncio.subprocess.Process:
    print(f"[Launcher] Starting service: {name} ({' '.join(cmd)})", flush=True)
    return await asyncio.create_subprocess_exec(*cmd)


async def main() -> None:
    port = os.getenv("PORT", "8000")
    print("==========================================================", flush=True)
    print("  KRAKEN Single-Container Standalone Launcher (Free Tier)", flush=True)
    print("==========================================================", flush=True)

    processes: list[asyncio.subprocess.Process] = []

    # 1. Start internal backend microservices
    for name, cmd in SERVICES:
        proc = await run_process(name, cmd)
        processes.append(proc)
        await asyncio.sleep(1.5)  # Stagger startup slightly

    # 2. Start Gateway microservice on public $PORT
    gateway_cmd = [
        "uvicorn",
        "services.gateway.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        port,
    ]
    print(f"[Launcher] Starting public Gateway on 0.0.0.0:{port}...", flush=True)
    gateway_proc = await run_process("gateway", gateway_cmd)
    processes.append(gateway_proc)

    # 3. Wait for all processes (exit if any process dies)
    try:
        await asyncio.gather(*[p.wait() for p in processes])
    except KeyboardInterrupt:
        print("[Launcher] Shutting down all microservices...", flush=True)
        for p in processes:
            p.terminate()


if __name__ == "__main__":
    asyncio.run(main())

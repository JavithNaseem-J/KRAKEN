"""
Single-container process manager for KRAKEN.
Runs all 7 microservices in a single Python process using concurrent Uvicorn Server instances.
This reduces RAM usage from ~450MB (7 separate OS processes) down to ~120MB (1 shared Python process),
enabling rock-solid execution on Render's 512MB Free Tier.

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
from pathlib import Path

# Ensure workspace root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Ensure localhost URLs are permitted for internal intra-container communication
os.environ["ORCHESTRATOR_URL"] = os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:8001")
os.environ["KNOWLEDGE_URL"] = os.getenv("KNOWLEDGE_URL", "http://127.0.0.1:8002")
os.environ["ACTION_URL"] = os.getenv("ACTION_URL", "http://127.0.0.1:8003")
os.environ["APPROVAL_URL"] = os.getenv("APPROVAL_URL", "http://127.0.0.1:8004")
os.environ["MEMORY_URL"] = os.getenv("MEMORY_URL", "http://127.0.0.1:8005")
os.environ["AUDIT_URL"] = os.getenv("AUDIT_URL", "http://127.0.0.1:8006")
os.environ["APPROVAL_BASE_URL"] = os.getenv("APPROVAL_BASE_URL", "http://127.0.0.1:8004")
os.environ["HITL_SERVICE_TOKEN"] = os.getenv(
    "HITL_SERVICE_TOKEN", "4f8a9c3e2b1d0e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f"
)

# Set single-container environment flag
os.environ["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "dev")

import uvicorn

# Import all FastAPI apps in a single Python process to share module memory space (~120MB total RSS)
from services.action.main import app as action_app
from services.approval.main import app as approval_app
from services.audit.main import app as audit_app
from services.gateway.main import app as gateway_app
from services.knowledge.main import app as knowledge_app
from services.memory.main import app as memory_app
from services.orchestrator.main import app as orchestrator_app


async def serve_service(name: str, server: uvicorn.Server) -> None:
    try:
        await server.serve()
    except SystemExit as exc:
        print(f"[Launcher] Service '{name}' exited with code {exc.code}", flush=True)
    except Exception as exc:
        print(f"[Launcher] Service '{name}' failed: {exc}", flush=True)


async def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    print("==========================================================", flush=True)
    print("  KRAKEN Single-Container Standalone Launcher (Free Tier)", flush=True)
    print("  Single-Process Shared Memory Mode (~120MB RSS)", flush=True)
    print("==========================================================", flush=True)

    configs = [
        ("audit", uvicorn.Config(audit_app, host="127.0.0.1", port=8006, log_level="warning")),
        ("memory", uvicorn.Config(memory_app, host="127.0.0.1", port=8005, log_level="warning")),
        ("approval", uvicorn.Config(approval_app, host="127.0.0.1", port=8004, log_level="warning")),
        ("action", uvicorn.Config(action_app, host="127.0.0.1", port=8003, log_level="warning")),
        ("knowledge", uvicorn.Config(knowledge_app, host="127.0.0.1", port=8002, log_level="warning")),
        ("orchestrator", uvicorn.Config(orchestrator_app, host="127.0.0.1", port=8001, log_level="warning")),
        ("gateway", uvicorn.Config(gateway_app, host="0.0.0.0", port=port, log_level="info")),
    ]

    tasks = []
    for name, cfg in configs:
        print(f"[Launcher] Starting in-process service: {name} ({cfg.host}:{cfg.port})", flush=True)
        server = uvicorn.Server(cfg)
        tasks.append(serve_service(name, server))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("[Launcher] Shutting down all in-process microservices...", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

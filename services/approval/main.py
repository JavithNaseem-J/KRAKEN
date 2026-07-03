"""
Approval Service — full implementation with Redis queue and background timeout checker.

Lifecycle:
  startup  → connect to Redis, create ApprovalQueue, start timeout checker task
  shutdown → cancel checker task, close Redis connection

Endpoints:
  POST /pending                         Called by executor node — enqueues action for approval
  GET  /approve/{approval_id}           Renders the human-facing approval web UI
  POST /approve/{approval_id}/decision  Processes approve/reject form submission
  GET  /health                          Liveness probe
  GET  /queue/stats                     Ops visibility — count of pending approvals

Timeout handling:
  A background asyncio task runs every 60 seconds, checks for expired entries,
  and sends a "timeout" callback to the orchestrator so the graph can resume
  and cancel the action gracefully.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx
import structlog
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from shared.config import get_settings
from .queue import ApprovalQueue
from .notifier import print_approval_notice

log      = structlog.get_logger(__name__)
settings = get_settings()

templates = Jinja2Templates(directory="templates")


# ── Background timeout checker ─────────────────────────────────────────────────
async def _timeout_checker(queue: ApprovalQueue) -> None:
    """
    Runs every 60 seconds. Detects TTL-expired approvals and sends
    "timeout" callbacks so the orchestrator can resume and cancel.
    """
    while True:
        await asyncio.sleep(60)
        try:
            expired = await queue.get_expired()
            for entry in expired:
                approval_id = entry.get("approval_id", "")
                session_id  = entry.get("session_id",  "")
                log.warning(
                    "approval.timeout",
                    approval_id=approval_id,
                    session_id=session_id,
                )
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{settings.orchestrator_url}/approval-callback",
                            json={"approval_id": approval_id, "decision": "timeout"},
                        )
                except Exception as exc:
                    log.error("approval.timeout_callback_failed", error=str(exc))
        except Exception as exc:
            log.error("approval.timeout_checker_error", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── Connect to Redis ───────────────────────────────────────────────────────
    log.info("approval.startup", redis_url=settings.redis_url)
    queue = ApprovalQueue(
        redis_url=settings.redis_url,
        timeout_seconds=settings.approval_timeout_seconds,
    )
    app.state.queue = queue

    # ── Start background timeout checker ──────────────────────────────────────
    checker = asyncio.create_task(_timeout_checker(queue))
    log.info("approval.timeout_checker_started", interval_seconds=60)

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    checker.cancel()
    try:
        await checker
    except asyncio.CancelledError:
        pass
    await queue.close()
    log.info("approval.shutdown")


app = FastAPI(
    title="AKEA Approval",
    description="HITL Approval Service — Autonomous Knowledge Execution Agent",
    version="0.5.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "approval"}


@app.get("/queue/stats", tags=["ops"])
async def queue_stats() -> dict[str, Any]:
    """Return pending approval count from Redis index."""
    queue: ApprovalQueue = app.state.queue
    try:
        import redis.asyncio as aioredis
        count = await queue._redis.scard("akea:approval:index")
        return {"pending_approvals": count, "timeout_seconds": settings.approval_timeout_seconds}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/pending", tags=["hitl"])
async def create_pending(payload: dict[str, Any]) -> dict[str, str]:
    """
    Enqueue a new approval request. Called by the executor node.
    Prints approval URL to terminal immediately.
    """
    queue: ApprovalQueue = app.state.queue

    action_name = payload.get("action_name", "unknown")
    approval_id = await queue.enqueue(
        action_name=action_name,
        payload=payload.get("payload", {}),
        reasoning=payload.get("reasoning", ""),
        session_id=payload.get("session_id", ""),
    )

    approval_url = print_approval_notice(
        approval_id=approval_id,
        action_name=action_name,
        approval_port=settings.approval_port,
        timeout_minutes=settings.approval_timeout_seconds // 60,
    )

    return {"approval_id": approval_id, "url": approval_url}


@app.get("/approve/{approval_id}", response_class=HTMLResponse, tags=["hitl"])
async def approval_page(request: Request, approval_id: str) -> HTMLResponse:
    """Render the human-facing approval UI."""
    queue: ApprovalQueue = app.state.queue
    entry = await queue.get(approval_id)

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found, already resolved, or expired.",
        )

    return templates.TemplateResponse(
        "approval.html",
        {
            "request":     request,
            "approval_id": approval_id,
            "action":      entry,
        },
    )


@app.post("/approve/{approval_id}/decision", tags=["hitl"])
async def submit_decision(
    approval_id: str,
    decision:    str = Form(...),
) -> dict[str, str]:
    """
    Process the approve/reject form. Resolves the queue entry,
    then POSTs the decision to the orchestrator callback.
    """
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'.")

    queue: ApprovalQueue = app.state.queue
    entry = await queue.resolve(approval_id)

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found, already resolved, or expired.",
        )

    session_id = entry.get("session_id", "")
    log.info(
        "approval.decision",
        approval_id=approval_id,
        decision=decision,
        session_id=session_id,
    )

    # ── Notify orchestrator (non-blocking — fire and don't wait too long) ──────
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.orchestrator_url}/approval-callback",
                json={"approval_id": approval_id, "decision": decision},
            )
    except Exception as exc:
        log.error("approval.callback_failed", error=str(exc), approval_id=approval_id)
        # Don't raise — the decision was recorded; callback failure is non-fatal

    return {
        "approval_id": approval_id,
        "decision":    decision,
        "status":      "sent",
        "session_id":  session_id,
    }

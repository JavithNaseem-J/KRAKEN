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
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from shared.config import get_settings

from .notifier import print_approval_notice
from .queue import ApprovalQueue

log = structlog.get_logger(__name__)
settings = get_settings()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Request Models ────────────────────────────────────────────────────────────
class PendingApprovalRequest(BaseModel):
    action_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    session_id: str


# ── Dependency: Enforce Service Token Auth ────────────────────────────────────
def _verify_service_token(
    x_service_token: str | None = Header(None, alias="X-Service-Token"),
) -> str:
    """
    Enforce high-privilege service token authentication.
    Uses timing-attack safe comparison.
    """
    token = x_service_token or ""
    if not token or not secrets.compare_digest(token, settings.hitl_service_token):
        log.warning("approval.auth_failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing service token.",
        )
    return token


# ── Helper: Notify Orchestrator Callback with Retry/Backoff ───────────────────
async def _notify_orchestrator_callback(
    client: httpx.AsyncClient,
    approval_id: str,
    decision: str,
    max_retries: int = 3,
) -> bool:
    """
    Send approval decision (approve, reject, or timeout) to orchestrator.
    Attempts with linear backoff retry on failure.
    """
    url = f"{settings.orchestrator_url}/approval-callback"
    payload = {"approval_id": approval_id, "decision": decision}
    headers = {"X-Service-Token": settings.hitl_service_token}

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
            resp.raise_for_status()
            log.info(
                "approval.callback_success",
                approval_id=approval_id,
                decision=decision,
                attempt=attempt,
            )
            return True
        except Exception as exc:
            backoff = attempt * 2.0
            log.warning(
                "approval.callback_retry",
                approval_id=approval_id,
                error=str(exc),
                attempt=attempt,
                next_retry_seconds=backoff,
            )
            if attempt < max_retries:
                await asyncio.sleep(backoff)

    log.error("approval.callback_exhausted", approval_id=approval_id, decision=decision)
    return False


# ── Background timeout checker ─────────────────────────────────────────────────
async def _timeout_checker(app: FastAPI) -> None:
    """
    Runs every 60 seconds. Detects TTL-expired approvals and sends
    "timeout" callbacks so the orchestrator can resume and cancel.
    """
    while True:
        await asyncio.sleep(60)
        queue: ApprovalQueue = app.state.queue
        client: httpx.AsyncClient = app.state.http
        try:
            expired = await queue.get_expired()
            for entry in expired:
                approval_id = entry.get("approval_id", "")
                session_id = entry.get("session_id", "")
                log.warning(
                    "approval.timeout",
                    approval_id=approval_id,
                    session_id=session_id,
                )
                # Dispatch notification in background task so we don't block the loop
                asyncio.create_task(_notify_orchestrator_callback(client, approval_id, "timeout"))
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

    # Verify Redis connectivity at boot
    if not await queue.ping():
        log.critical("approval.redis_connection_failed")
        raise RuntimeError("Failed to connect to Redis during startup.")

    app.state.queue = queue

    # ── Shared HTTP client for callbacks ──────────────────────────────────────
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
    )

    # ── Start background timeout checker ──────────────────────────────────────
    checker = asyncio.create_task(_timeout_checker(app))
    log.info("approval.timeout_checker_started", interval_seconds=60)

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    checker.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await checker

    await queue.close()
    await app.state.http.aclose()
    log.info("approval.shutdown")


app = FastAPI(
    title="AKEA Approval",
    description="HITL Approval Service — Autonomous Knowledge Execution Agent",
    version="0.6.0",
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
        count = await queue.stats()
        return {"pending_approvals": count, "timeout_seconds": settings.approval_timeout_seconds}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/pending", tags=["hitl"])
async def create_pending(
    req: PendingApprovalRequest,
    _token: str = Depends(_verify_service_token),
) -> dict[str, str]:
    """
    Enqueue a new approval request. Called by the executor node.
    Requires service token verification.
    """
    queue: ApprovalQueue = app.state.queue

    approval_id = await queue.enqueue(
        action_name=req.action_name,
        payload=req.payload,
        reasoning=req.reasoning,
        session_id=req.session_id,
    )

    approval_url = print_approval_notice(
        approval_id=approval_id,
        action_name=req.action_name,
        approval_base_url=settings.approval_base_url,
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
        request=request,
        name="approval.html",
        context={
            "approval_id": approval_id,
            "action": entry,
        },
    )


@app.post("/approve/{approval_id}/decision", tags=["hitl"])
async def submit_decision(
    approval_id: str,
    decision: str = Form(...),
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

    # Notify orchestrator using the persistent HTTP client and retry logic
    # Runs in the background so we return the HTML form result immediately without waiting
    client: httpx.AsyncClient = app.state.http
    asyncio.create_task(_notify_orchestrator_callback(client, approval_id, decision))

    return {
        "approval_id": approval_id,
        "decision": decision,
        "status": "sent",
        "session_id": session_id,
    }

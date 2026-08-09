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
import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from shared.auth import verify_service_token
from shared.config import get_settings
from shared.http_client import create_async_http_client, service_headers
from shared.logging import configure_logging

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


# ── Helper: Notify Orchestrator Callback with Retry/Backoff ───────────────────
async def _notify_orchestrator_callback(
    client: httpx.AsyncClient,
    approval_id: str,
    decision: str,
    max_retries: int = 3,
) -> bool:
    """
    Send approval decision (approve or reject) to orchestrator.
    Attempts with linear backoff retry on failure.
    """
    url = f"{settings.orchestrator_url}/approval-callback"
    payload = {"approval_id": approval_id, "decision": decision}
    headers = service_headers()

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="approval"
    )
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
    app.state.http = create_async_http_client()

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    await queue.close()
    await app.state.http.aclose()
    log.info("approval.shutdown")


from shared.middleware.rate_limit import RateLimitMiddleware
from shared.middleware.trace_id import TraceIdMiddleware

app = FastAPI(
    title="KRAKEN Approval",
    description="HITL Approval Service — KRAKEN",
    version="0.6.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)
app.add_middleware(RateLimitMiddleware, path_prefix="/approve/", max_requests=60, window_seconds=60)

# ── CORS (React frontend origins) ─────────────────────────────────────────────
# Required so the React SPA can fetch approval details/CSRF token and submit
# inline approval decisions directly from the browser.
allowed_cors_origins = [
    origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-Id"],
)


@app.get("/", tags=["ops"])
async def root() -> dict[str, Any]:
    return {
        "service": "approval",
        "description": "KRAKEN Human-in-the-Loop (HITL) Approval Service",
        "documentation": "/docs",
        "pending_approvals": "/pending",
        "queue_stats": "/queue/stats",
        "frontend": "http://localhost:5173",
    }


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "approval"}


@app.get("/queue/stats", tags=["ops"])
async def queue_stats(
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
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
    _token: str = Depends(verify_service_token),
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


@app.get("/approve/{approval_id}/details", tags=["hitl"])
async def approval_details(approval_id: str) -> dict[str, Any]:
    """Return JSON details and CSRF token for a pending approval request."""
    queue: ApprovalQueue = app.state.queue
    entry = await queue.get(approval_id)

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found, already resolved, or expired.",
        )

    csrf_token = secrets.token_hex(16)
    await queue.set_csrf_token(approval_id, csrf_token)

    return {
        "approval_id": approval_id,
        "action_name": entry.get("action_name", ""),
        "payload": entry.get("payload", {}),
        "reasoning": entry.get("reasoning", ""),
        "session_id": entry.get("session_id", ""),
        "status": entry.get("status", "PENDING"),
        "created_at": entry.get("created_at"),
        "csrf_token": csrf_token,
    }


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

    csrf_token = secrets.token_hex(16)
    await queue.set_csrf_token(approval_id, csrf_token)

    return templates.TemplateResponse(
        request=request,
        name="approval.html",
        context={
            "approval_id": approval_id,
            "action": entry,
            "csrf_token": csrf_token,
        },
    )


@app.post("/approve/{approval_id}/decision", response_class=HTMLResponse, tags=["hitl"])
async def submit_decision(
    request: Request,
    approval_id: str,
    decision: str = Form(...),
    csrf_token: str = Form(...),
) -> HTMLResponse:
    """
    Process the approve/reject form. Resolves the queue entry,
    then POSTs the decision to the orchestrator callback.
    """
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'.")

    if not csrf_token or not csrf_token.strip():
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")

    queue: ApprovalQueue = app.state.queue

    valid_csrf = await queue.verify_csrf_token(approval_id, csrf_token)
    if not valid_csrf:
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")
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
    task = asyncio.create_task(_notify_orchestrator_callback(client, approval_id, decision))
    task.add_done_callback(
        lambda t: log.error(
            "approval.callback_task_exception",
            approval_id=approval_id,
            error=str(t.exception()),
        )
        if not t.cancelled() and t.exception()
        else None
    )

    return templates.TemplateResponse(
        request=request,
        name="decision_done.html",
        context={"approval_id": approval_id, "decision": decision, "session_id": session_id},
    )

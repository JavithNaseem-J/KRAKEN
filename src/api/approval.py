from __future__ import annotations

import os
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.safety.policy_engine import get_policy_engine
from src.utils.approval.notifier import print_approval_notice
from src.utils.approval.queue import ApprovalQueue
from src.utils.auth import verify_service_token
from src.utils.config import get_settings
from src.utils.cors import cors_middleware_kwargs
from src.utils.http_client import (
    create_async_http_client,
    get_app_http_client,
    internal_request,
    service_headers,
    simple_health_response,
)
from src.utils.logging import configure_logging
from src.utils.middleware.rate_limit import RateLimitMiddleware
from src.utils.middleware.trace_id import TraceIdMiddleware
from src.utils.privacy import strip_reasoning_fields
from src.utils.registry import get_action

log = structlog.get_logger(__name__)
settings = get_settings()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "..", "utils", "approval", "templates")
)


# Request Models
class PendingApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str | None = None
    action_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    session_id: str
    initiator_id: str = ""
    initiator_role: str = "end_user"

    @field_validator("payload", mode="before")
    @classmethod
    def remove_private_reasoning(cls, value: Any) -> Any:
        return strip_reasoning_fields(value)


# Helper: Notify Orchestrator Callback with Retry/Backoff
async def _notify_orchestrator_callback(
    client: httpx.AsyncClient,
    approval_id: str,
    decision: str,
    session_id: str = "",
    approver_role: str | None = None,
    approver_id: str | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """
    Send approval decision (approve or reject) to orchestrator.
    Routed through the shared internal helper, which short-circuits in-process
    and retries only on transport errors / 5xx (4xx such as 409 idempotency
    conflicts are never retried).
    """
    url = f"{settings.orchestrator_url}/approval-callback"
    payload = {
        "approval_id": approval_id,
        "decision": decision,
        "session_id": session_id,
        "approver_role": approver_role,
        "approver_id": approver_id,
    }
    headers = service_headers()

    try:
        resp = await internal_request(
            "POST",
            url,
            json_payload=payload,
            headers=headers,
            timeout_seconds=60.0,
            client=client,
        )
        data = resp.json() if resp.status_code == 200 else None
        log.info(
            "approval.callback_success",
            approval_id=approval_id,
            decision=decision,
        )
        return True, data
    except Exception as exc:
        log.error(
            "approval.callback_exhausted",
            approval_id=approval_id,
            decision=decision,
            error=str(exc),
        )
        return False, None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="approval"
    )
    # Connect to Redis
    log.info("approval.startup", redis_url=settings.redis_url)
    queue = ApprovalQueue(
        redis_url=settings.redis_url,
        timeout_seconds=settings.approval_timeout_seconds,
    )

    # Verify Redis connectivity at boot
    if not await queue.ping():
        log.warning("approval.redis_connection_failed_running_degraded")
    await queue.purge_legacy_reasoning_entries()

    app.state.queue = queue

    # Shared HTTP client for callbacks
    app.state.http = create_async_http_client()

    yield

    # Shutdown
    await queue.close()
    await app.state.http.aclose()
    log.info("approval.shutdown")


app = FastAPI(
    title="KRAKEN Approval",
    description="HITL Approval Service — KRAKEN",
    version="0.6.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)
app.add_middleware(RateLimitMiddleware, path_prefix="/approve/", max_requests=60, window_seconds=60)

# CORS (React frontend origins)
# Required so the React SPA can fetch approval details/CSRF token and submit
# inline approval decisions directly from the browser.
app.add_middleware(
    CORSMiddleware,
    **cors_middleware_kwargs(),
)


def _get_queue() -> ApprovalQueue:
    """Return initialized approval queue with lazy fallback."""
    queue = getattr(app.state, "queue", None)
    if queue is None:
        queue = ApprovalQueue(
            redis_url=settings.redis_url,
            timeout_seconds=settings.approval_timeout_seconds,
        )
        app.state.queue = queue
    return queue


def _approval_policy_details(action_name: str) -> tuple[str, str]:
    """Return registry-derived approval information without model-generated text."""
    try:
        risk_level = get_action(action_name).risk_level.value
    except Exception:
        risk_level = "CRITICAL"
    approval_reason = (
        f"This {risk_level} action requires approval by an eligible operator "
        "other than the initiator before execution."
    )
    return risk_level, approval_reason


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
    return simple_health_response("approval")


@app.get("/queue/stats", tags=["ops"])
async def queue_stats(
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Return pending approval count from Redis index."""
    queue = _get_queue()
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
    queue = _get_queue()

    approval_id = await queue.enqueue(
        action_name=req.action_name,
        payload=req.payload,
        session_id=req.session_id,
        initiator_id=req.initiator_id,
        initiator_role=req.initiator_role,
        approval_id=req.approval_id,
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
    queue = _get_queue()
    entry = await queue.get(approval_id)

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found, already resolved, or expired.",
        )

    csrf_token = secrets.token_hex(16)
    await queue.set_csrf_token(approval_id, csrf_token)
    risk_level, approval_reason = _approval_policy_details(entry.get("action_name", ""))

    return {
        "approval_id": approval_id,
        "action_name": entry.get("action_name", ""),
        "payload": strip_reasoning_fields(entry.get("payload", {})),
        "risk_level": risk_level,
        "approval_reason": approval_reason,
        "session_id": entry.get("session_id", ""),
        "status": entry.get("status", "PENDING"),
        "created_at": entry.get("created_at"),
        "initiator_id": entry.get("initiator_id", ""),
        "initiator_role": entry.get("initiator_role", "end_user"),
        "csrf_token": csrf_token,
    }


@app.get("/approve/{approval_id}", response_class=HTMLResponse, tags=["hitl"])
async def approval_page(request: Request, approval_id: str) -> HTMLResponse:
    """Render the human-facing approval UI."""
    queue = _get_queue()
    entry = await queue.get(approval_id)

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Approval request not found, already resolved, or expired.",
        )

    csrf_token = secrets.token_hex(16)
    await queue.set_csrf_token(approval_id, csrf_token)
    risk_level, approval_reason = _approval_policy_details(entry.get("action_name", ""))

    return templates.TemplateResponse(
        request=request,
        name="approval.html",
        context={
            "approval_id": approval_id,
            "action": entry,
            "action_name": entry.get("action_name", ""),
            "risk_level": risk_level,
            "approval_reason": approval_reason,
            "csrf_token": csrf_token,
        },
    )


@app.post(
    "/approve/{approval_id}/decision",
    response_class=HTMLResponse,
    response_model=None,
    tags=["hitl"],
)
async def submit_decision(
    request: Request,
    approval_id: str,
    decision: str = Form(...),
    csrf_token: str = Form(...),
    approver_role: str | None = Form(None),
    approver_id: str | None = Form(None),
    expected_session_id: str | None = Form(None),
) -> HTMLResponse | JSONResponse:
    """
    Process the approve/reject form. Resolves the queue entry,
    then POSTs the decision to the orchestrator callback with approver attribution.
    """
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'.")

    if not csrf_token or not csrf_token.strip():
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")

    queue = _get_queue()

    valid_csrf = await queue.verify_csrf_token(approval_id, csrf_token)
    if not valid_csrf:
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")

    # Retrieve entry to validate action clearance before resolving
    entry_peek = await queue.get(approval_id)
    if expected_session_id and (
        entry_peek is None
        or not secrets.compare_digest(str(entry_peek.get("session_id", "")), expected_session_id)
    ):
        raise HTTPException(status_code=404, detail="Approval request not found.")
    action_name = entry_peek.get("action_name", "") if entry_peek else ""
    initiator_id = entry_peek.get("initiator_id", "") if entry_peek else ""
    if (
        decision == "approve"
        and initiator_id
        and secrets.compare_digest(initiator_id, approver_id or "")
    ):
        raise HTTPException(
            status_code=403,
            detail="The initiating actor cannot approve the same critical action.",
        )

    # Declarative Policy-as-Code Four-Eyes clearance evaluation
    policy_eval = get_policy_engine().evaluate_approval_decision(
        action_name=action_name,
        approver_role=approver_role,
        decision=decision,
    )
    if not policy_eval.allowed:
        log.warning(
            "approval.policy_denied",
            approval_id=approval_id,
            approver_role=approver_role,
            reason=policy_eval.reason,
        )
        raise HTTPException(
            status_code=policy_eval.status_code,
            detail=policy_eval.reason,
        )

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
        approver_role=approver_role,
        approver_id=approver_id,
    )

    # Notify orchestrator using the persistent HTTP client and retry logic
    client = get_app_http_client(app)
    success, agent_response = await _notify_orchestrator_callback(
        client,
        approval_id,
        decision,
        session_id=session_id,
        approver_role=approver_role,
        approver_id=approver_id,
    )

    accept_header = request.headers.get("accept", "")
    if "json" in accept_header or accept_header == "application/json":
        return JSONResponse(
            content={
                "status": "ok" if success else "error",
                "approval_id": approval_id,
                "decision": decision,
                "session_id": session_id,
                "agent_response": agent_response,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="decision_done.html",
        context={"approval_id": approval_id, "decision": decision, "session_id": session_id},
    )

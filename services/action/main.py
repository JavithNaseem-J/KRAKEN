"""
Action Service — full implementation with registry dispatch and audit integration.

Execution lifecycle for every action:
  1. Look up action in registry (raises 404 if unknown)
  2. Validate payload has required parameters
  3. Dispatch to the appropriate handler
  4. Fire audit log (non-blocking, best-effort)
  5. Return ActionResult

All errors are caught, converted to ActionResult(success=False), and audited.
Exceptions never propagate as 500s — the orchestrator needs a structured result.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException

from shared.config import get_settings
from shared.exceptions import (
    ActionExecutionError,
    ActionNotFoundError,
    InvalidExtensionError,
    PathTraversalError,
)
from shared.models.action import ActionRequest, ActionResult, ActionType
from .registry import get_action
from .handlers.read_handler import read_ticket, read_ticket_list
from .handlers.write_handler import write_json_file
from .audit_client import fire_audit_log

log = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("action.startup")
    yield
    log.info("action.shutdown")


app = FastAPI(
    title="AKEA Action",
    description="Action Execution Service — Autonomous Knowledge Execution Agent",
    version="0.4.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "action"}


@app.get("/registry", tags=["actions"])
async def list_actions() -> dict:
    """Return the complete action registry for inspection."""
    from .registry import REGISTRY
    return {
        name: {
            "description":  defn.description,
            "action_type":  defn.action_type.value,
            "risk_level":   defn.risk_level.value,
            "requires_hitl": defn.requires_hitl,
        }
        for name, defn in REGISTRY.items()
    }


@app.post("/execute", response_model=ActionResult, tags=["actions"])
async def execute(body: ActionRequest) -> ActionResult:
    """
    Execute a registered action and write to the audit log.

    WRITE actions reaching this endpoint have already been approved by a human
    (the executor node in the orchestrator calls /execute only after HITL approval).
    """
    log.info(
        "action.execute",
        action=body.action_name,
        session_id=body.session_id,
        user_id=body.user_id,
    )

    # ── 1. Registry lookup ────────────────────────────────────────────────────
    try:
        action_def = get_action(body.action_name)
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    # ── 2. Dispatch ───────────────────────────────────────────────────────────
    result_data: dict[str, Any] | None = None
    status = "failure"
    error_msg: str | None = None

    try:
        result_data = _dispatch(body.action_name, body.payload)
        status = "success"
        log.info("action.success", action=body.action_name, session_id=body.session_id)

    except (PathTraversalError, InvalidExtensionError) as exc:
        error_msg = str(exc)
        log.error("action.safety_violation", action=body.action_name, error=error_msg)

    except ActionExecutionError as exc:
        error_msg = exc.message
        log.error("action.execution_error", action=body.action_name, error=error_msg)

    except Exception as exc:
        error_msg = f"Unexpected error: {exc}"
        log.error("action.unexpected_error", action=body.action_name, error=error_msg)

    # ── 3. Audit log (non-blocking thread) ────────────────────────────────────
    threading.Thread(
        target=fire_audit_log,
        kwargs={
            "session_id":    body.session_id,
            "user_id":       body.user_id,
            "action_type":   action_def.action_type.value,
            "action_name":   body.action_name,
            "risk_level":    action_def.risk_level.value,
            "hitl_required": action_def.requires_hitl,
            "hitl_decision": "approved" if action_def.requires_hitl else None,
            "status":        status,
            "reasoning":     body.reasoning,
            "payload":       body.payload,
            "result":        result_data,
        },
        daemon=True,
    ).start()

    # ── 4. Return structured result ───────────────────────────────────────────
    return ActionResult(
        action_name=body.action_name,
        success=status == "success",
        result=result_data,
        error=error_msg,
    )


def _dispatch(action_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Route action name to the correct handler function.
    Raises ActionExecutionError on missing required parameters.
    """
    if action_name == "read_ticket":
        ticket_id = payload.get("ticket_id")
        if not ticket_id:
            raise ActionExecutionError("read_ticket requires 'ticket_id' in payload.")
        ticket = read_ticket(str(ticket_id))
        return {"ticket": ticket}

    elif action_name == "read_ticket_list":
        tickets = read_ticket_list(
            status=payload.get("status"),
            priority=payload.get("priority"),
            category=payload.get("category"),
            limit=int(payload.get("limit", 10)),
        )
        return {"tickets": tickets, "count": len(tickets)}

    elif action_name == "write_json_file":
        target_path = payload.get("target_path")
        content     = payload.get("content")
        if not target_path:
            raise ActionExecutionError("write_json_file requires 'target_path' in payload.")
        if not isinstance(content, dict):
            raise ActionExecutionError("write_json_file requires 'content' to be a JSON object.")
        return write_json_file(str(target_path), content)

    else:
        raise ActionExecutionError(f"No handler registered for action '{action_name}'.")

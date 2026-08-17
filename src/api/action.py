from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException

from src.tools.ticket import (
    execute_auto_respond,
    execute_close,
    execute_create_ticket,
    execute_escalate,
    execute_request_info,
)
from src.tools.write_tool import write_json_file
from src.utils.audit_client import fire_audit_log
from src.utils.auth import verify_service_token
from src.utils.config import get_settings
from src.utils.exceptions import (
    ActionExecutionError,
    ActionNotFoundError,
    InvalidExtensionError,
    PathTraversalError,
)
from src.utils.http_client import create_async_http_client
from src.utils.logging import configure_logging
from src.utils.middleware.trace_id import TraceIdMiddleware
from src.utils.models.action import ActionRequest, ActionResult
from src.utils.registry import REGISTRY, get_action

log = structlog.get_logger(__name__)
settings = get_settings()


# ── Dependency: Enforce Service Token Auth ────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="action"
    )
    log.info("action.startup")

    # Persistent HTTP client for outgoing audit logging calls
    app.state.http = create_async_http_client()

    if settings.postgres_sync_url or settings.postgres_url:
        try:
            from src.utils.db import create_sync_pool, ensure_schema_sync

            sync_url = settings.postgres_sync_url or settings.postgres_url
            pool = create_sync_pool(sync_url)
            ensure_schema_sync(pool)
            pool.close()
        except Exception as exc:
            log.warning("action.schema_bootstrap_failed", error=str(exc))

    yield

    await app.state.http.aclose()
    log.info("action.shutdown")


app = FastAPI(
    title="KRAKEN Action",
    description="Action Execution Service — KRAKEN",
    version="0.5.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "action"}


@app.get("/registry", tags=["actions"])
async def list_actions() -> dict:
    """Return the complete action registry for inspection."""
    return {
        name: {
            "description": defn.description,
            "action_type": defn.action_type.value,
            "risk_level": defn.risk_level.value,
            "requires_hitl": defn.requires_hitl,
        }
        for name, defn in REGISTRY.items()
    }


@app.post("/execute", response_model=ActionResult, tags=["actions"])
async def execute(
    body: ActionRequest,
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_service_token),
) -> ActionResult:
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
    status_str = "failure"
    error_msg: str | None = None

    try:
        result_data = await asyncio.to_thread(_dispatch, body.action_name, body.payload)
        status_str = "success"
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

    # ── 3. Audit log (non-blocking BackgroundTask) ────────────────────────────
    client: httpx.AsyncClient = app.state.http
    background_tasks.add_task(
        fire_audit_log,
        client=client,
        session_id=body.session_id,
        user_id=body.user_id,
        action_type=action_def.action_type.value,
        action_name=body.action_name,
        risk_level=action_def.risk_level.value,
        hitl_required=action_def.requires_hitl,
        hitl_decision="approved" if action_def.requires_hitl else None,
        status=status_str,
        reasoning=body.reasoning,
        payload=body.payload,
        result=result_data,
    )

    # ── 4. Return structured result ───────────────────────────────────────────
    return ActionResult(
        action_name=body.action_name,
        success=status_str == "success",
        result=result_data,
        error=error_msg,
    )


HANDLER_MAP: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "auto_respond": lambda p: execute_auto_respond(
        p.get("ticket_id"), p.get("response_text", ""), p.get("evidence", "")
    ),
    "escalate": lambda p: execute_escalate(
        p.get("ticket_id", ""), p.get("reason", ""), p.get("evidence", "")
    ),
    "request_info": lambda p: execute_request_info(
        p.get("ticket_id", ""), p.get("info_requested", ""), p.get("evidence", "")
    ),
    "close": lambda p: execute_close(
        p.get("ticket_id", ""), p.get("reason", ""), p.get("evidence", "")
    ),
    "create_ticket": lambda p: execute_create_ticket(
        user_name=p.get("user_name", p.get("user", "")),
        category=p.get("category", "IT Support"),
        priority=p.get("priority", "medium"),
        description=p.get("description", p.get("reason", "")),
        evidence=p.get("evidence", ""),
    ),
    "write_json_file": lambda p: write_json_file(
        p.get("target_path", ""), p.get("content", {})
    ),
}


def validate_action_payload(action_name: str, payload: dict[str, Any]) -> None:
    """Validate action payload against registry parameter_schema."""
    action_def = get_action(action_name)
    if not action_def:
        raise ActionNotFoundError(f"Action '{action_name}' is not registered.")

    schema = action_def.parameter_schema
    for param, expected_type in schema.items():
        val = payload.get(param)
        if "str" in expected_type and "None" not in expected_type and val is not None:
            if not isinstance(val, str):
                raise ActionExecutionError(
                    f"Invalid payload parameter '{param}': expected string, got {type(val).__name__}"
                )
        elif "dict" in expected_type and val is not None and not isinstance(val, dict):
            raise ActionExecutionError(
                f"Invalid payload parameter '{param}': expected dict, got {type(val).__name__}"
            )


def _dispatch(action_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Route action name to the correct handler function via HANDLER_MAP lookup after payload validation.
    """
    validate_action_payload(action_name, payload)
    handler = HANDLER_MAP.get(action_name)
    if not handler:
        raise ActionExecutionError(f"No handler registered for action '{action_name}'.")
    return handler(payload)

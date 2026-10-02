from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException

from src.safety.policy_engine import get_policy_engine
from src.tools.ticket import (
    execute_auto_respond,
    execute_close,
    execute_create_ticket,
    execute_escalate,
    execute_get_ticket_status,
    execute_request_info,
    get_pg_pool,
    quarantine_ip_handler,
    unlock_account_handler,
)
from src.utils.approval.queue import ApprovalQueue
from src.utils.audit.client import fire_audit_log
from src.utils.auth import verify_service_token
from src.utils.config import get_settings
from src.utils.exceptions import (
    ActionExecutionError,
    ActionNotFoundError,
)
from src.utils.http_client import (
    create_async_http_client,
    get_app_http_client,
    simple_health_response,
)
from src.utils.logging import configure_logging
from src.utils.middleware.trace_id import TraceIdMiddleware
from src.utils.models.action import ActionDefinition, ActionRequest, ActionResult, RiskLevel
from src.utils.registry import ACTION_POLICY_METADATA, REGISTRY, get_action
from src.utils.synthetic_tickets import (
    SyntheticTicketRepository,
    synthetic_ticket_repository,
)

log = structlog.get_logger(__name__)
settings = get_settings()


# Dependency: Enforce Service Token Auth


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Per-service lifespan: configure logging, create shared HTTP client, yield, teardown.

    Each API module deliberately owns its own lifespan rather than sharing a factory.
    This keeps services independently deployable and avoids hidden coupling between
    startup sequencing concerns. See CONTRIBUTING.md § "Service lifespan pattern".
    """
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="action"
    )
    log.info("action.startup")

    ticket_pool = await asyncio.to_thread(get_pg_pool)
    log.info("action.synthetic_ticket_store", persistent=ticket_pool is not None)

    # Persistent HTTP client for outgoing audit logging calls
    app.state.http = create_async_http_client()
    app.state.approval_queue = ApprovalQueue(
        redis_url=settings.redis_url,
        timeout_seconds=settings.approval_timeout_seconds,
    )
    yield

    await app.state.approval_queue.close()
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
    return simple_health_response("action")


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


async def _authorize_critical_action(
    body: ActionRequest, action_def: ActionDefinition
) -> tuple[dict[str, Any] | None, ActionResult | None]:
    if not (action_def.requires_hitl or action_def.risk_level == RiskLevel.CRITICAL):
        return None, None
    if not body.approval_id:
        raise HTTPException(status_code=403, detail="Verified approval is required.")

    queue: ApprovalQueue = app.state.approval_queue
    try:
        decision = await queue.get_decision(body.approval_id)
    except Exception as exc:
        log.error("action.approval_store_unavailable", error=exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Approval verification unavailable.") from exc

    initiator_id = body.public_actor_id or body.user_id
    try:
        valid = bool(
            decision
            and decision.get("decision") == "approve"
            and decision.get("approval_id") == body.approval_id
            and decision.get("action_name") == body.action_name
            and decision.get("payload") == body.payload
            and decision.get("session_id") == body.session_id
            and (decision.get("public_session_id") or None) == body.public_session_id
            and decision.get("initiator_id") == initiator_id
            and decision.get("dataset_generation") == settings.synthetic_dataset_generation
            and decision.get("approver_id")
            and decision.get("approver_role")
            and datetime.fromisoformat(str(decision.get("expires_at"))) > datetime.now(UTC)
        )
    except (TypeError, ValueError):
        valid = False
    if valid and decision is not None:
        policy = get_policy_engine().evaluate_approval_decision(
            body.action_name, str(decision["approver_role"]), "approve"
        )
        valid = policy.allowed and not (
            ACTION_POLICY_METADATA[body.action_name]["requires_four_eyes"]
            and decision["approver_id"] == decision["initiator_id"]
        )
    if not valid:
        raise HTTPException(status_code=403, detail="Approval does not authorize this action.")

    try:
        claim_status, stored = await queue.claim_execution(body.approval_id)
    except Exception as exc:
        log.error("action.approval_claim_unavailable", error=exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Approval verification unavailable.") from exc
    if claim_status == "complete" and stored is not None:
        return decision, ActionResult.model_validate(stored)
    if claim_status != "claimed":
        raise HTTPException(status_code=409, detail="Approved execution is already in progress.")
    return decision, None


@app.post("/execute", response_model=ActionResult, tags=["actions"])
async def execute(
    body: ActionRequest,
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_service_token),
) -> ActionResult:
    """
    Execute a registered action synchronously or dispatch to background task.
    Enforces service-token authentication.
    Logs execution result to the audit service asynchronously.
    """
    # 1. Registry lookup
    try:
        action_def = get_action(body.action_name)
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    verified_approval, replayed_result = await _authorize_critical_action(body, action_def)
    if replayed_result is not None:
        return replayed_result

    # 2. Dispatch
    result_data: dict[str, Any] | None = None
    status_str = "failure"
    error_msg: str | None = None

    try:
        if body.public_session_id:
            result_data = await asyncio.to_thread(
                _dispatch_synthetic,
                body.action_name,
                body.payload,
                body.public_session_id,
                synthetic_ticket_repository,
            )
        else:
            result_data = await asyncio.to_thread(_dispatch, body.action_name, body.payload)
        status_str = "failure" if result_data.get("success") is False else "success"
        log.info("action.success", action=body.action_name, session_id=body.session_id)

    except ActionExecutionError as exc:
        error_msg = "Action execution failed."
        log.error("action.execution_error", action=body.action_name, error=exc.__class__.__name__)

    except Exception as exc:
        error_msg = "Action execution failed."
        log.error("action.unexpected_error", action=body.action_name, error=exc.__class__.__name__)

    action_result = ActionResult(
        action_name=body.action_name,
        success=status_str == "success",
        result=result_data,
        error=error_msg,
    )
    if verified_approval and body.approval_id:
        try:
            await app.state.approval_queue.complete_execution(
                body.approval_id, action_result.model_dump(mode="json")
            )
        except Exception as exc:
            log.error("action.approval_result_store_failed", error=exc.__class__.__name__)

    # 3. Audit log (non-blocking BackgroundTask)
    client = get_app_http_client(app)
    audit_result = dict(result_data or {})
    if verified_approval:
        audit_result["approval"] = {
            "approval_id": body.approval_id,
            "approver_id": verified_approval["approver_id"],
            "approver_role": verified_approval["approver_role"],
        }
    background_tasks.add_task(
        fire_audit_log,
        client=client,
        session_id=body.session_id,
        user_id=body.user_id,
        action_type=action_def.action_type.value,
        action_name=body.action_name,
        risk_level=action_def.risk_level.value,
        hitl_required=action_def.requires_hitl,
        hitl_decision="approved" if verified_approval else None,
        status=status_str,
        payload=body.payload,
        result=audit_result,
    )

    # 4. Return structured result
    return action_result


HANDLER_MAP: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "auto_respond": lambda p: execute_auto_respond(
        p.get("ticket_id"), p.get("response_text", ""), p.get("evidence", "")
    ),
    "get_ticket_status": lambda p: execute_get_ticket_status(p.get("ticket_id", "")),
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
    "quarantine_ip": lambda p: quarantine_ip_handler(
        ip=p.get("ip", ""), reason=p.get("reason"), evidence=p.get("evidence")
    ),
    "unlock_account": lambda p: unlock_account_handler(
        user_email=p.get("user_email", p.get("email", p.get("user", ""))),
        reason=p.get("reason"),
        evidence=p.get("evidence"),
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


def _dispatch_synthetic(
    action_name: str,
    payload: dict[str, Any],
    session_id: str,
    repository: SyntheticTicketRepository,
) -> dict[str, Any]:
    """Execute only generation-scoped synthetic environment adapters."""
    validate_action_payload(action_name, payload)
    if action_name == "create_ticket":
        return repository.create(session_id, payload)
    if action_name == "get_ticket_status":
        ticket = repository.get(session_id, str(payload.get("ticket_id", "")))
        return {
            "success": True,
            "action": action_name,
            "synthetic": True,
            "dataset_generation": settings.synthetic_dataset_generation,
            **ticket,
        }
    if action_name == "close":
        return repository.mutate(
            session_id,
            str(payload.get("ticket_id", "")),
            status="closed",
            updates={"closure_reason": str(payload.get("reason", ""))},
        )
    if action_name == "escalate":
        return repository.mutate(
            session_id,
            str(payload.get("ticket_id", "")),
            status="escalated",
            updates={"escalation_reason": str(payload.get("reason", ""))},
        )
    if action_name == "request_info":
        return repository.mutate(
            session_id,
            str(payload.get("ticket_id", "")),
            status="pending",
            updates={"info_requested": str(payload.get("info_requested", ""))},
        )
    if action_name == "quarantine_ip":
        repository.consume_write(session_id)
        return quarantine_ip_handler(
            ip=str(payload.get("ip", "")),
            reason=str(payload.get("reason", "")),
            evidence=str(payload.get("evidence", "")),
        )
    if action_name == "unlock_account":
        repository.consume_write(session_id)
        return unlock_account_handler(
            user_email=str(payload.get("user_email") or payload.get("user") or ""),
            reason=str(payload.get("reason", "")),
            evidence=str(payload.get("evidence", "")),
        )
    if action_name == "auto_respond":
        return {
            "success": True,
            "action": "auto_respond",
            "synthetic": True,
            "dataset_generation": settings.synthetic_dataset_generation,
            "response": str(payload.get("response_text", "")),
            "evidence_cited": str(payload.get("evidence", "")),
        }
    raise ActionExecutionError(f"Action '{action_name}' is unavailable in this demo application.")

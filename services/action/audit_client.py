"""
Audit client — fire-and-forget HTTP call to the audit service.

Used by the action service after every action execution.
Failures are logged but never propagated — the action result must not be
blocked by an audit write failure.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from shared.config import get_settings

log = structlog.get_logger(__name__)


async def fire_audit_log(
    client: httpx.AsyncClient,
    session_id: str,
    user_id: str,
    action_type: str,
    action_name: str,
    risk_level: str,
    hitl_required: bool,
    status: str,
    reasoning: str | None = None,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    hitl_decision: str | None = None,
) -> None:
    """
    POST an audit entry to the audit service.
    Called in a BackgroundTask using the app's persistent AsyncClient.
    """
    settings = get_settings()
    entry = {
        "session_id": session_id,
        "user_id": user_id,
        "action_type": action_type,
        "action_name": action_name,
        "risk_level": risk_level,
        "hitl_required": hitl_required,
        "hitl_decision": hitl_decision,
        "status": status,
        "reasoning": reasoning,
        "payload": payload,
        "result": result,
    }
    try:
        headers = {"X-Service-Token": settings.hitl_service_token}
        resp = await client.post(f"{settings.audit_url}/log", json=entry, headers=headers)
        resp.raise_for_status()
    except Exception as exc:
        # Audit failure must not affect action result
        log.error("audit_client.failed", error=str(exc), action=action_name)

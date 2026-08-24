from __future__ import annotations

from typing import Any

import httpx
import structlog

from src.utils.config import get_settings
from src.utils.http_client import internal_request, service_headers
from src.utils.logging import summarize_audit_data
from src.utils.models.audit import AuditLogRequest

log = structlog.get_logger(__name__)
settings = get_settings()


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
    req = AuditLogRequest(
        session_id=session_id,
        user_id=user_id,
        action_type=action_type,
        action_name=action_name,
        risk_level=risk_level,
        hitl_required=hitl_required,
        status=status,
        reasoning=None,
        payload=summarize_audit_data(payload),
        result=summarize_audit_data(result),
        hitl_decision=hitl_decision,
    )
    try:
        headers = service_headers()
        await internal_request(
            "POST",
            f"{settings.audit_url}/log",
            json_payload=req.model_dump(mode="json"),
            headers=headers,
            client=client,
        )
    except Exception as exc:
        # Audit failure must not affect action result
        log.error("audit_client.failed", error=exc.__class__.__name__, action=action_name)

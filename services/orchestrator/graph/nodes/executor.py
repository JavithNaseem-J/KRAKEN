"""
Executor Node — dispatches the selected action to the action service.

HITL Gate:
  If risk_level == "CRITICAL", this node calls the approval service and uses
  LangGraph's interrupt() to pause the graph. The graph only resumes when the
  orchestrator receives the approval callback and calls graph.invoke(Command(resume=...)).

  If risk_level == "SAFE", the action service is called directly.

For "respond_only" actions, execution is skipped entirely.
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog
from langgraph.types import interrupt

from shared.config import get_settings
from shared.models.action import ActionRequest
from services.orchestrator.graph.state import GraphState

log = structlog.get_logger(__name__)
settings = get_settings()


def executor_node(state: GraphState) -> dict:
    session_id      = state.get("session_id", "")
    action_name     = state.get("selected_action", "auto_respond")
    action_payload  = state.get("action_payload") or {}
    risk_level      = state.get("risk_level", "SAFE")
    reasoning       = state.get("reasoning", "")
    user_id         = state.get("user_id", "system")

    log.info(
        "executor.start",
        session_id=session_id,
        action=action_name,
        risk=risk_level,
    )

    # ── Respond-only: no action service call needed ────────────────────────────
    if action_name == "respond_only":
        log.info("executor.respond_only", session_id=session_id)
        return {"action_result": None, "approval_status": None}

    # ── CRITICAL: pause graph until human approves ─────────────────────────────
    if risk_level == "CRITICAL":
        approval_id = _register_approval(
            action_name=action_name,
            payload=action_payload,
            reasoning=reasoning,
            session_id=session_id,
        )
        # interrupt() suspends graph here — resumes via Command(resume=decision)
        decision: dict[str, str] = interrupt({
            "approval_id": approval_id,
            "action_name": action_name,
            "payload":     action_payload,
        })

        decision_value = decision.get("decision", "reject")
        log.info(
            "executor.hitl_decision",
            session_id=session_id,
            approval_id=approval_id,
            decision=decision_value,
        )

        if decision_value != "approve":
            return {
                "approval_id":     approval_id,
                "approval_status": decision_value,
                "action_result":   {"cancelled": True, "reason": "Human rejected or timed out"},
            }

        return {
            "approval_id":     approval_id,
            "approval_status": "approved",
            "action_result":   _call_action_service(
                action_name, action_payload, session_id, user_id, reasoning
            ),
        }

    # ── SAFE: call action service directly ────────────────────────────────────
    return {
        "approval_status": None,
        "action_result":   _call_action_service(
            action_name, action_payload, session_id, user_id, reasoning
        ),
    }


def _register_approval(
    action_name: str,
    payload: dict[str, Any],
    reasoning: str,
    session_id: str,
) -> str:
    """Call approval service to register pending action. Returns approval_id."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{settings.approval_url}/pending",
                json={
                    "action_name": action_name,
                    "payload":     payload,
                    "reasoning":   reasoning,
                    "session_id":  session_id,
                },
            )
            resp.raise_for_status()
            return resp.json()["approval_id"]
    except Exception as exc:
        log.error("executor.approval_register_failed", error=str(exc))
        raise


def _call_action_service(
    action_name: str,
    payload: dict[str, Any],
    session_id: str,
    user_id: str,
    reasoning: str,
) -> dict[str, Any]:
    """POST to action service /execute and return the result dict."""
    request = ActionRequest(
        action_name=action_name,
        payload=payload,
        session_id=session_id,
        user_id=user_id,
        reasoning=reasoning,
    )
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{settings.action_url}/execute",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.error("executor.action_failed", action=action_name, error=str(exc))
        return {"success": False, "error": str(exc)}

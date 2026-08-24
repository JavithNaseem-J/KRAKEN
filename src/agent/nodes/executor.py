from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx
import structlog
from langgraph.types import interrupt

from src.agent.state import GraphState
from src.utils.config import get_settings
from src.utils.http_client import post_with_retry, service_headers
from src.utils.models.action import ActionRequest

log = structlog.get_logger(__name__)
settings = get_settings()


async def _register_approval(
    client: httpx.AsyncClient,
    action_name: str,
    payload: dict[str, Any],
    reasoning: str,
    session_id: str,
    initiator_id: str,
    initiator_role: str,
    approval_id: str,
) -> str:
    """Call approval service to register pending action. Returns approval_id."""
    resp = await post_with_retry(
        client,
        f"{settings.approval_url}/pending",
        {
            "action_name": action_name,
            "payload": payload,
            "reasoning": reasoning,
            "session_id": session_id,
            "initiator_id": initiator_id,
            "initiator_role": initiator_role,
            "approval_id": approval_id,
        },
        headers=service_headers(trace_id=session_id),
    )
    return resp.json()["approval_id"]


async def _call_action_service(
    client: httpx.AsyncClient,
    action_name: str,
    payload: dict[str, Any],
    session_id: str,
    user_id: str,
    reasoning: str,
    demo_session_id: str | None = None,
    demo_actor_id: str | None = None,
) -> dict[str, Any]:
    """POST to action service /execute and return the result dict."""
    request = ActionRequest(
        action_name=action_name,
        payload=payload,
        session_id=session_id,
        user_id=user_id,
        reasoning=reasoning,
        demo_session_id=demo_session_id,
        demo_actor_id=demo_actor_id,
    )
    try:
        resp = await post_with_retry(
            client,
            f"{settings.action_url}/execute",
            request.model_dump(),
            headers=service_headers(trace_id=session_id),
        )
        return resp.json()
    except Exception as exc:
        log.error("executor.action_failed", action=action_name, error=str(exc))
        return {"success": False, "error": str(exc)}


async def executor_node(state: GraphState) -> dict:
    """
    Dispatch the selected action(s) to the action service.
    CRITICAL actions pause execution via LangGraph interrupt() until human approval arrives.
    SAFE actions are executed concurrently via asyncio.gather.
    """
    session_id = state.get("session_id", "")
    selected_actions = state.get("selected_actions") or []
    primary_action = state.get("selected_action")
    action_payload = state.get("action_payload") or {}
    risk_level = state.get("risk_level", "SAFE")
    reasoning = state.get("reasoning", "")
    user_id = state.get("user_id", "system")
    operator_role = state.get("operator_role", "end_user")
    demo_session_id = state.get("demo_session_id") or None
    demo_actor_id = state.get("demo_actor_id") or None
    execution_id = state.get("execution_id") or f"{session_id}:{state.get('user_message', '')}"

    if not selected_actions and primary_action:
        selected_actions = [
            {
                "action_name": primary_action,
                "action_payload": action_payload,
                "risk_level": risk_level,
            }
        ]

    log.info(
        "executor.start",
        session_id=session_id,
        action_count=len(selected_actions),
        risk=risk_level,
    )

    if not selected_actions:
        log.info("executor.skip_no_action", session_id=session_id)
        return {"action_result": None, "approval_status": None}

    async with httpx.AsyncClient(timeout=30.0) as client:
        safe_actions = [a for a in selected_actions if a.get("risk_level") == "SAFE"]
        critical_actions = [a for a in selected_actions if a.get("risk_level") == "CRITICAL"]

        results: list[dict[str, Any]] = []

        # Concurrent SAFE Action Execution
        if safe_actions:
            log.info("executor.safe_parallel_dispatch", count=len(safe_actions))
            tasks = [
                _call_action_service(
                    client,
                    act["action_name"],
                    act.get("action_payload", {}),
                    session_id,
                    user_id,
                    reasoning,
                    demo_session_id,
                    demo_actor_id,
                )
                for act in safe_actions
            ]
            safe_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in safe_results:
                if isinstance(res, dict):
                    results.append(res)
                else:
                    results.append({"success": False, "error": str(res)})

        # CRITICAL: pause graph until human approves
        if critical_actions:
            crit_act = critical_actions[0]
            c_name = crit_act["action_name"]
            c_payload = crit_act.get("action_payload", {})
            approval_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"kraken:{execution_id}:{c_name}:{json.dumps(c_payload, sort_keys=True)}",
                )
            )
            try:
                approval_id = await _register_approval(
                    client=client,
                    action_name=c_name,
                    payload=c_payload,
                    reasoning=reasoning,
                    session_id=session_id,
                    initiator_id=demo_actor_id or user_id,
                    initiator_role=operator_role,
                    approval_id=approval_id,
                )
            except Exception as exc:
                log.error("executor.approval_register_failed", error=str(exc))
                return {
                    "approval_status": "failed",
                    "action_result": {
                        "success": False,
                        "error": f"Failed to register approval request: {exc}",
                    },
                    "error": f"Failed to register approval request: {exc}",
                }

            # interrupt() suspends graph here — resumes via Command(resume=decision)
            decision: dict[str, str] = interrupt(
                {
                    "approval_id": approval_id,
                    "action_name": c_name,
                    "payload": c_payload,
                }
            )

            decision_value = decision.get("decision", "reject")
            log.info(
                "executor.hitl_decision",
                session_id=session_id,
                approval_id=approval_id,
                decision=decision_value,
            )

            if decision_value != "approve":
                results.append({"cancelled": True, "reason": f"Human decision: {decision_value}"})
                return {
                    "approval_id": approval_id,
                    "approval_status": decision_value,
                    "action_result": results[0] if len(results) == 1 else results,
                }

            crit_res = await _call_action_service(
                client,
                c_name,
                c_payload,
                session_id,
                user_id,
                reasoning,
                demo_session_id,
                demo_actor_id,
            )
            results.append(crit_res)
            return {
                "approval_id": approval_id,
                "approval_status": "approved",
                "action_result": results[0] if len(results) == 1 else results,
            }

        return {
            "approval_status": None,
            "action_result": results[0] if len(results) == 1 else results,
        }

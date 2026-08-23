from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agent.state import GraphState
from src.prompts.registry import get_prompt
from src.safety.policy_engine import should_override_to_auto_respond
from src.utils.config import get_settings
from src.utils.llm import get_llm
from src.utils.registry import REGISTRY, get_action

log = structlog.get_logger(__name__)
settings = get_settings()


def _get_available_actions_prompt() -> str:
    """Build the list of available actions dynamically from the registry."""
    lines = []
    for name, defn in REGISTRY.items():
        params = ", ".join(f"{k}: {v}" for k, v in defn.parameter_schema.items())
        risk_str = f"Risk: {defn.risk_level.value}"
        if defn.requires_hitl:
            risk_str += " — requires human approval"
        lines.append(f"{name} — {defn.description} Parameters: [{params}]. {risk_str}.")
    return "\n".join(lines)


class ActionDecision(BaseModel):
    selected_action: str = "auto_respond"
    action_payload: dict = Field(default_factory=dict)


class DecisionOutput(BaseModel):
    selected_action: str = "auto_respond"
    selected_actions: list[ActionDecision] = Field(default_factory=list)
    action_payload: dict = Field(default_factory=dict)
    evidence: str = ""
    explanation: str = ""



async def decider_node(state: GraphState) -> dict:
    """
    Select action + validate risk level against registry.
    Risk level is ALWAYS determined by the registry, never by the LLM.
    """
    session_id = state.get("session_id", "")
    log.info("decider.start", session_id=session_id)

    user_message = state.get("user_message", "")
    reasoning = state.get("reasoning", "No reasoning available.")

    human_content = f"User request: {user_message}\n\nAnalysis:\n{reasoning}"

    try:
        available_actions = _get_available_actions_prompt()
        system_prompt = get_prompt("decider", "SYSTEM_PROMPT_TEMPLATE").format(
            available_actions=available_actions
        )

        structured_llm = get_llm().with_structured_output(DecisionOutput, method="json_mode")
        decision: DecisionOutput = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content),
            ]
        )

        action_name = decision.selected_action.strip() if decision.selected_action else ""

        # Build verified actions list
        raw_actions = (
            decision.selected_actions if isinstance(decision.selected_actions, list) else []
        )
        payload = decision.action_payload if isinstance(decision.action_payload, dict) else {}
        actions_to_process = raw_actions or [
            ActionDecision(selected_action=action_name, action_payload=payload)
        ]

        should_override, is_status_query = should_override_to_auto_respond(
            user_message, action_name
        )
        if should_override:
            log.info(
                "decider.override_action_to_auto_respond",
                original_action=action_name,
                is_status_query=is_status_query,
                query=user_message[:50],
            )
            action_name = "auto_respond"
            actions_to_process = [
                ActionDecision(selected_action="auto_respond", action_payload={})
            ]

        verified_actions: list[dict[str, Any]] = []
        highest_risk: str = "SAFE"

        for act in actions_to_process:
            if isinstance(act, ActionDecision):
                act_name = act.selected_action.strip() if act.selected_action else ""
                act_payload = act.action_payload if isinstance(act.action_payload, dict) else {}
            elif isinstance(act, dict):
                act_name = str(act.get("action_name") or act.get("selected_action") or "").strip()
                act_payload = (
                    act.get("action_payload") if isinstance(act.get("action_payload"), dict) else {}
                )
            else:
                act_name = str(
                    getattr(act, "selected_action", getattr(act, "action_name", "")) or ""
                ).strip()
                act_payload = getattr(act, "action_payload", {})
                if not isinstance(act_payload, dict):
                    act_payload = {}

            if act_name in REGISTRY:
                act_def = get_action(act_name)
                act_risk = act_def.risk_level.value
                if act_risk == "CRITICAL":
                    highest_risk = "CRITICAL"
                payload = dict(act_payload)
                payload["evidence"] = str(decision.evidence) if decision.evidence else ""
                payload["explanation"] = str(decision.explanation) if decision.explanation else ""
                verified_actions.append(
                    {
                        "action_name": act_name,
                        "action_payload": payload,
                        "risk_level": act_risk,
                    }
                )

        if not verified_actions:
            log.error(
                "decider.invalid_action_hallucinated", session_id=session_id, action=action_name
            )
            return {
                "selected_action": None,
                "selected_actions": [],
                "action_payload": None,
                "risk_level": None,
                "evidence": decision.evidence,
                "error": f"Decider hallucinated unregistered action '{action_name}'.",
            }

        primary_action = verified_actions[0]
        evidence = decision.evidence or primary_action["action_payload"].get("evidence", "")

        log.info(
            "decider.done",
            session_id=session_id,
            action=primary_action["action_name"],
            total_actions=len(verified_actions),
            highest_risk=highest_risk,
        )

        return {
            "selected_action": primary_action["action_name"],
            "selected_actions": verified_actions,
            "action_payload": primary_action["action_payload"],
            "risk_level": highest_risk,
            "evidence": evidence,
        }

    except Exception as exc:
        log.error("decider.error", session_id=session_id, error=str(exc))
        return {
            "selected_action": None,
            "action_payload": None,
            "risk_level": None,
            "evidence": None,
            "error": f"Triage decision failed: {exc}",
        }

from __future__ import annotations

import re
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agent.state import GraphState
from src.prompts.registry import get_prompt
from src.safety.policy_engine import get_policy_engine, should_override_to_auto_respond
from src.utils.config import get_settings
from src.utils.constants import TICKET_ID_REGEX
from src.utils.llm import get_llm, invoke_llm
from src.utils.registry import REGISTRY, get_action

log = structlog.get_logger(__name__)
settings = get_settings()

_STATUS_QUERY_KEYWORDS: tuple[str, ...] = (
    "status of",
    "ticket status",
    "check status",
    "what is the status",
)
_IP_ADDRESS_REGEX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _ticket_status_fast_path(user_message: str) -> dict[str, Any] | None:
    msg_lower = user_message.lower()
    if not any(keyword in msg_lower for keyword in _STATUS_QUERY_KEYWORDS):
        return None

    match = TICKET_ID_REGEX.search(user_message)
    if not match:
        return None

    ticket_id = match.group(0).upper()
    payload = {"ticket_id": ticket_id}
    return {
        "selected_action": "get_ticket_status",
        "selected_actions": [
            {
                "action_name": "get_ticket_status",
                "action_payload": payload,
                "risk_level": "SAFE",
            }
        ],
        "action_payload": payload,
        "risk_level": "SAFE",
        "evidence": f"Read-only ticket status lookup requested for {ticket_id}.",
    }


def _priority_from_message(user_message: str) -> str:
    msg_lower = user_message.lower()
    if any(term in msg_lower for term in ("critical", "p1", "sev1")):
        return "critical"
    if any(term in msg_lower for term in ("high", "p2", "sev2")):
        return "high"
    if any(term in msg_lower for term in ("medium", "p3", "normal")):
        return "medium"
    if any(term in msg_lower for term in ("low", "p4")):
        return "low"
    return "medium"


def _category_from_message(user_message: str) -> str:
    msg_lower = user_message.lower()
    if "vpn" in msg_lower or "globalprotect" in msg_lower:
        return "VPN"
    if any(term in msg_lower for term in ("monitor", "laptop", "hardware", "keyboard", "mouse")):
        return "Hardware"
    if any(term in msg_lower for term in ("account", "password", "login", "mfa")):
        return "Identity & Access"
    if "security" in msg_lower or "vulnerability" in msg_lower:
        return "Security"
    return "IT Support"


def _user_from_message(user_message: str) -> str:
    match = re.search(
        r"\bfor\s+(?:user\s+)?([A-Z][A-Za-z0-9_.-]{1,40}(?:\s+[A-Z][A-Za-z0-9_.-]{1,40})?)",
        user_message,
    )
    if match:
        return match.group(1).strip().rstrip(".")
    return "Demo User"


def _description_from_message(user_message: str) -> str:
    if ":" in user_message:
        tail = user_message.split(":", 1)[1].strip()
        if tail:
            return tail
    cleaned = re.sub(
        r"(?i)\b(create|open)\s+(?:an?\s+)?(?:it\s+|support\s+)?ticket\s+(?:for\s+)?",
        "",
        user_message,
    ).strip()
    return cleaned or user_message.strip()


def _create_ticket_fast_path(user_message: str) -> dict[str, Any] | None:
    msg_lower = user_message.lower()
    if not re.search(r"\b(create|open)\b", msg_lower) or "ticket" not in msg_lower:
        return None

    payload = {
        "user_name": _user_from_message(user_message),
        "category": _category_from_message(user_message),
        "priority": _priority_from_message(user_message),
        "description": _description_from_message(user_message),
        "evidence": "User explicitly requested a synthetic demo ticket.",
    }
    return {
        "selected_action": "create_ticket",
        "selected_actions": [
            {
                "action_name": "create_ticket",
                "action_payload": payload,
                "risk_level": "SAFE",
            }
        ],
        "action_payload": payload,
        "risk_level": "SAFE",
        "evidence": payload["evidence"],
    }


def _quarantine_ip_fast_path(user_message: str, operator_role: str) -> dict[str, Any] | None:
    msg_lower = user_message.lower()
    if "quarantine" not in msg_lower and "block" not in msg_lower:
        return None

    match = _IP_ADDRESS_REGEX.search(user_message)
    if not match:
        return None

    payload = {
        "ip": match.group(0),
        "reason": _description_from_message(user_message),
        "evidence": "User supplied a concrete IP and stated malicious activity in the demo flow.",
    }
    policy_decision = get_policy_engine().evaluate_action_staging(
        "quarantine_ip",
        operator_role,
        payload,
    )
    if not policy_decision.allowed:
        return {
            "selected_action": None,
            "selected_actions": [],
            "action_payload": None,
            "risk_level": None,
            "evidence": payload["evidence"],
            "error": policy_decision.reason,
        }
    return {
        "selected_action": "quarantine_ip",
        "selected_actions": [
            {
                "action_name": "quarantine_ip",
                "action_payload": payload,
                "risk_level": "CRITICAL",
            }
        ],
        "action_payload": payload,
        "risk_level": "CRITICAL",
        "evidence": payload["evidence"],
    }


def _deterministic_action_fast_path(user_message: str, operator_role: str) -> dict[str, Any] | None:
    for candidate in (
        _ticket_status_fast_path(user_message),
        _create_ticket_fast_path(user_message),
        _quarantine_ip_fast_path(user_message, operator_role),
    ):
        if candidate is not None:
            return candidate
    return None


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
    operator_role = state.get("operator_role", "end_user")
    reasoning = state.get("reasoning", "No reasoning available.")

    fast_path = _deterministic_action_fast_path(user_message, operator_role)
    if fast_path is not None:
        log.info(
            "decider.deterministic_fast_path",
            session_id=session_id,
            action=fast_path.get("selected_action"),
        )
        return fast_path

    human_content = f"User request: {user_message}\n\nAnalysis:\n{reasoning}"

    try:
        available_actions = _get_available_actions_prompt()
        system_prompt = get_prompt("decider", "SYSTEM_PROMPT_TEMPLATE").format(
            available_actions=available_actions
        )

        structured_llm = get_llm().with_structured_output(DecisionOutput, method="json_mode")
        decision: DecisionOutput = await invoke_llm(
            structured_llm,
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content),
            ],
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
                ActionDecision(
                    selected_action="auto_respond",
                    action_payload={
                        "ticket_id": None,
                        "response_text": f"Direct response for query: {user_message[:100]}",
                        "evidence": "Knowledge base verified documentation.",
                    },
                )
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

            action_override, _ = should_override_to_auto_respond(user_message, act_name)
            if action_override:
                log.warning(
                    "decider.unrequested_write_action_removed",
                    session_id=session_id,
                    action=act_name,
                )
                continue

            if act_name in REGISTRY:
                act_def = get_action(act_name)
                policy_decision = get_policy_engine().evaluate_action_staging(
                    act_name,
                    operator_role,
                    act_payload,
                )
                if not policy_decision.allowed:
                    log.warning(
                        "decider.policy_staging_denied",
                        session_id=session_id,
                        action=act_name,
                        operator_role=operator_role,
                        reason=policy_decision.reason,
                    )
                    return {
                        "selected_action": None,
                        "selected_actions": [],
                        "action_payload": None,
                        "risk_level": None,
                        "evidence": decision.evidence,
                        "error": policy_decision.reason,
                    }
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
        log.error("decider.error", session_id=session_id, error=exc.__class__.__name__)
        return {
            "selected_action": None,
            "action_payload": None,
            "risk_level": None,
            "evidence": None,
            "error": "llm_provider_unavailable",
        }

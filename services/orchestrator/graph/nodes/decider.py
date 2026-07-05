"""
Decider Node — selects the appropriate action using structured LLM output.

Uses with_structured_output() to force the LLM to return a valid Pydantic model.
This is the critical node: its output determines whether HITL fires.

Action selection rules (enforced here, not left to LLM discretion):
  - "respond_only" → SAFE, no HITL, no action service call.
  - "read_*"       → SAFE, no HITL.
  - "write_*"      → CRITICAL, HITL always fires.

The LLM proposes an action; the decider node validates it against the registry
and overrides the risk level based on the registered definition — never trusting
the LLM's risk assessment directly.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from services.action.registry import REGISTRY, get_action
from services.orchestrator.graph.state import GraphState
from services.orchestrator.llm import get_llm
from shared.config import get_settings

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
        lines.append(f"{name} — {defn.description} Parameters: {{{params}}}. {risk_str}.")
    return "\n".join(lines)


class DecisionOutput(BaseModel):
    selected_action: str = Field(description="Exact action name from the available list.")
    action_payload: dict = Field(
        default_factory=dict,
        description="Parameters for the action. You must populate the parameters matching the schema of the selected action.",
    )
    evidence: str = Field(
        description="Verbatim citation or specific facts from the retrieved knowledge base that led to this decision (e.g. specific SLA guidelines, security policies, audit details, or ticket status)."
    )
    explanation: str = Field(
        description="A detailed explanation justifying why this action was chosen based on the retrieved evidence. Do not summarize; show your step-by-step reasoning."
    )


_SYSTEM_PROMPT_TEMPLATE = """You are the lead security triage decider for Xiarch, a cybersecurity consultancy.

Based on the user request, the ticket details, and the retrieved knowledge base chunks, choose the most appropriate action and provide the specific facts (evidence) and explanation justifying your choice.

Available actions:
{available_actions}

Rules:
1. CITATION REQUIREMENT: You MUST locate and extract specific, verbatim facts from the retrieved knowledge chunks (e.g., SLA response times, pentesting rules of engagement, scoping requirements) to justify your choice. Put this in the 'evidence' field.
2. ACTION SELECTION CRITERIA:
   - Use 'auto_respond' when the inquiry is a general compliance, SLA, policy, or pentesting FAQ, or when a ticket can be resolved automatically using the retrieved facts.
   - Use 'escalate' if a ticket contains a critical vulnerability (e.g., RCE, SQLi, Auth Bypass), represents an active security incident, requires Tier 2/Senior/L3 review, or has breached SLA.
   - Use 'request_info' if the ticket details are insufficient (e.g., missing signed Rules of Engagement (RoE), missing IP ranges, missing configuration files).
   - Use 'close' if the client confirms that a security vulnerability is mitigated and the Associate/Consultant has verified the fix.
   - Use 'write_json_file' to store structured reports or results inside the workspace sandbox.
3. INJECT EVIDENCE IN PAYLOAD: You must always inject the extracted evidence into the 'evidence' key of the 'action_payload' dictionary for ticket triage actions.
"""


def decider_node(state: GraphState) -> dict:
    """
    Select action + validate risk level against registry.
    Risk level is ALWAYS determined by the registry, never by the LLM.
    """
    session_id = state.get("session_id", "")
    log.info("decider.start", session_id=session_id)

    user_message = state.get("user_message", "")
    reasoning = state.get("reasoning", "No reasoning available.")

    human_content = f"User request: {user_message}\n\n" f"Analysis:\n{reasoning}"

    try:
        available_actions = _get_available_actions_prompt()
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(available_actions=available_actions)

        structured_llm = get_llm().with_structured_output(DecisionOutput)
        decision: DecisionOutput = structured_llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content),
            ]
        )

        action_name = decision.selected_action.strip()

        # Fail-safe: validate selected action name is in registry
        if action_name not in REGISTRY:
            log.error(
                "decider.invalid_action_hallucinated", session_id=session_id, action=action_name
            )
            return {
                "selected_action": None,
                "action_payload": None,
                "risk_level": None,
                "evidence": decision.evidence,
                "error": f"Decider hallucinated unregistered action '{action_name}'.",
            }

        # Inject evidence and explanation into the payload if not set
        payload = decision.action_payload or {}
        payload["evidence"] = decision.evidence
        payload["explanation"] = decision.explanation

        # ── Risk level from registry — LLM's word is not trusted ──────────────
        action_def = get_action(action_name)
        risk_level = action_def.risk_level.value  # "SAFE" or "CRITICAL"
        requires_hitl = action_def.requires_hitl

        log.info(
            "decider.done",
            session_id=session_id,
            action=action_name,
            risk=risk_level,
            hitl=requires_hitl,
        )

        return {
            "selected_action": action_name,
            "action_payload": payload,
            "risk_level": risk_level,
            "evidence": decision.evidence,
        }

    except Exception as exc:
        log.error("decider.error", session_id=session_id, error=str(exc))
        # Honest fallback: Selected action = None, which routes straight to responder
        return {
            "selected_action": None,
            "action_payload": None,
            "risk_level": None,
            "evidence": None,
            "error": f"Triage decision failed: {exc}",
        }


def _resolve_risk_level(action_name: str) -> str:
    """
    Public helper: look up risk level from the action registry.
    Unknown actions default to CRITICAL as a fail-safe.
    Used by unit tests and the decider node internally.
    """
    try:
        action_def = get_action(action_name)
        return action_def.risk_level.value  # "SAFE" or "CRITICAL"
    except Exception:
        log.warning("decider.unknown_action_risk_lookup", action=action_name)
        return "CRITICAL"

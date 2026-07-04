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

from pydantic import BaseModel, Field

import structlog

from shared.config import get_settings
from services.orchestrator.graph.state import GraphState
from services.orchestrator.llm import get_llm

log = structlog.get_logger(__name__)
settings = get_settings()

# ── Action registry snapshot (imported here to avoid circular import) ─────────
_AVAILABLE_ACTIONS = """
auto_respond        — Resolve a ticket automatically or answer a general query by sending a drafted response backed by specific knowledge chunks. Parameters: {ticket_id: str | None, response_text: str, evidence: str}. Risk: SAFE.
escalate            — Escalate a ticket to senior security consultants or architects due to complexity, critical severity, or customer SLA urgency. Parameters: {ticket_id: str, reason: str, evidence: str}. Risk: CRITICAL — requires human approval.
request_info        — Request additional technical details or configuration parameters from the client before continuing testing or auditing. Parameters: {ticket_id: str, info_requested: str, evidence: str}. Risk: CRITICAL — requires human approval.
close               — Permanently close a ticket after the customer confirms the security vulnerability is resolved and fix is verified. Parameters: {ticket_id: str, reason: str, evidence: str}. Risk: CRITICAL — requires human approval.
"""


class DecisionOutput(BaseModel):
    selected_action: str = Field(
        description="Exact action name from the available list."
    )
    action_payload: dict = Field(
        default_factory=dict,
        description="Parameters for the action. You must populate the parameters matching the schema of the selected action, including 'evidence'."
    )
    evidence: str = Field(
        description="Verbatim citation or specific facts from the retrieved knowledge base that led to this decision (e.g. specific SLA guidelines, security policies, audit details, or ticket status)."
    )
    explanation: str = Field(
        description="A detailed explanation justifying why this action was chosen based on the retrieved evidence. Do not summarize; show your step-by-step reasoning."
    )


_SYSTEM_PROMPT = f"""You are the lead security triage decider for Xiarch, a cybersecurity consultancy.

Based on the user request, the ticket details, and the retrieved knowledge base chunks, choose the most appropriate action and provide the specific facts (evidence) and explanation justifying your choice.

Available actions:
{_AVAILABLE_ACTIONS}

Rules:
1. CITATION REQUIREMENT: You MUST locate and extract specific, verbatim facts from the retrieved knowledge chunks (e.g., SLA response times, pentesting rules of engagement, scoping requirements) to justify your choice. Put this in the 'evidence' field.
2. ACTION SELECTION CRITERIA:
   - Use 'auto_respond' when the inquiry is a general compliance, SLA, policy, or pentesting FAQ, or when a ticket can be resolved automatically using the retrieved facts.
   - Use 'escalate' if a ticket contains a critical vulnerability (e.g., RCE, SQLi, Auth Bypass), represents an active security incident, requires Tier 2/Senior/L3 review, or has breached SLA.
   - Use 'request_info' if the ticket details are insufficient (e.g., missing signed Rules of Engagement (RoE), missing IP ranges, missing configuration files).
   - Use 'close' if the client confirms that a security vulnerability is mitigated and the Associate/Consultant has verified the fix.
3. INJECT EVIDENCE IN PAYLOAD: You must always inject the extracted evidence into the 'evidence' key of the 'action_payload' dictionary.
"""


def decider_node(state: GraphState) -> dict:
    """
    Select action + validate risk level against registry.
    Risk level is ALWAYS determined by the registry, never by the LLM.
    """
    session_id = state.get("session_id", "")
    log.info("decider.start", session_id=session_id)

    user_message = state.get("user_message", "")
    reasoning    = state.get("reasoning", "No reasoning available.")

    human_content = (
        f"User request: {user_message}\n\n"
        f"Analysis:\n{reasoning}"
    )

    try:
        structured_llm = get_llm().with_structured_output(DecisionOutput)
        from langchain_core.messages import HumanMessage, SystemMessage
        decision: DecisionOutput = structured_llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])

        action_name = decision.selected_action.strip()

        # Inject evidence and explanation into the payload if not set
        payload = decision.action_payload or {}
        payload["evidence"] = decision.evidence
        payload["explanation"] = decision.explanation

        # ── Risk level from registry — LLM's word is not trusted ──────────────
        risk_level = _resolve_risk_level(action_name)
        requires_hitl = risk_level == "CRITICAL"

        log.info(
            "decider.done",
            session_id=session_id,
            action=action_name,
            risk=risk_level,
            hitl=requires_hitl,
        )

        return {
            "selected_action": action_name,
            "action_payload":  payload,
            "risk_level":      risk_level,
            "evidence":        decision.evidence,
        }

    except Exception as exc:
        log.error("decider.error", session_id=session_id, error=str(exc))
        return {
            "selected_action": "auto_respond",
            "action_payload":  {"response_text": "Error encountered during decision process.", "evidence": "System fallback"},
            "risk_level":      "SAFE",
            "evidence":        "System fallback due to error.",
            "error":           str(exc),
        }


def _resolve_risk_level(action_name: str) -> str:
    """
    Determine risk level from the registry — never from LLM output.
    Unknown actions default to CRITICAL as a fail-safe.
    """
    _RISK_MAP: dict[str, str] = {
        "auto_respond":     "SAFE",
        "escalate":         "CRITICAL",
        "request_info":     "CRITICAL",
        "close":            "CRITICAL",
    }
    level = _RISK_MAP.get(action_name)
    if level is None:
        log.warning("decider.unknown_action", action=action_name)
        return "CRITICAL"   # Unknown = treat as dangerous
    return level


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
from ..graph.state import GraphState
from ..llm import get_llm

log = structlog.get_logger(__name__)
settings = get_settings()

# ── Action registry snapshot (imported here to avoid circular import) ─────────
_AVAILABLE_ACTIONS = """
respond_only        — Answer the user question with no file changes. Risk: SAFE.
read_ticket         — Read a single ticket by ID. Parameters: {ticket_id: str}. Risk: SAFE.
read_ticket_list    — List tickets by filter. Parameters: {status?, priority?, category?, limit?}. Risk: SAFE.
write_json_file     — Write data to a .json file in the workspace. Parameters: {target_path: str, content: dict}. Risk: CRITICAL — requires human approval.
"""


class DecisionOutput(BaseModel):
    selected_action: str = Field(
        description="Exact action name from the available list. Use 'respond_only' if no action is needed."
    )
    action_payload: dict = Field(
        default_factory=dict,
        description="Parameters for the action. Empty dict for respond_only.",
    )
    explanation: str = Field(
        description="One sentence explaining why this action was selected."
    )


_SYSTEM_PROMPT = f"""You are a decision agent for an internal IT helpdesk system.

Based on the user's request and the analysis provided, select ONE action to take.

Available actions:
{_AVAILABLE_ACTIONS}

Rules:
- If the user is asking a question or seeking information → respond_only.
- If the user wants to update a ticket record → write_json_file with the updated data.
- If the user wants to look up a specific ticket → read_ticket.
- If the user wants to list tickets → read_ticket_list.
- Never invent actions not in the list above.
- For write_json_file, target_path must be a filename ending in .json (no directory traversal).
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
            "action_payload":  decision.action_payload,
            "risk_level":      risk_level,
        }

    except Exception as exc:
        log.error("decider.error", session_id=session_id, error=str(exc))
        return {
            "selected_action": "respond_only",
            "action_payload":  {},
            "risk_level":      "SAFE",
            "error":           str(exc),
        }


def _resolve_risk_level(action_name: str) -> str:
    """
    Determine risk level from the registry — never from LLM output.
    Unknown actions default to CRITICAL as a fail-safe.
    """
    _RISK_MAP: dict[str, str] = {
        "respond_only":     "SAFE",
        "read_ticket":      "SAFE",
        "read_ticket_list": "SAFE",
        "write_json_file":  "CRITICAL",
    }
    level = _RISK_MAP.get(action_name)
    if level is None:
        log.warning("decider.unknown_action", action=action_name)
        return "CRITICAL"   # Unknown = treat as dangerous
    return level

"""
Action registry — maps action names to their definitions.
Phase 4 populates this with real handlers.

RISK CLASSIFICATION RULES (enforced here, not in the LLM):
  READ  → SAFE     → no HITL
  WRITE → CRITICAL → HITL always required, no exceptions
"""
from __future__ import annotations

from shared.models.action import ActionDefinition, ActionType, RiskLevel

REGISTRY: dict[str, ActionDefinition] = {
    "auto_respond": ActionDefinition(
        name="auto_respond",
        description="Resolve a ticket automatically or answer a general query by sending a drafted response backed by specific knowledge chunks. Safe to execute without human approval.",
        action_type=ActionType.READ,
        risk_level=RiskLevel.SAFE,
        requires_hitl=False,
        parameter_schema={
            "ticket_id": "str | None",
            "response_text": "str",
            "evidence": "str"
        },
    ),
    "escalate": ActionDefinition(
        name="escalate",
        description="Escalate a ticket to senior security consultants or architects due to complexity, critical severity, or customer SLA urgency.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={
            "ticket_id": "str",
            "reason": "str",
            "evidence": "str"
        },
    ),
    "request_info": ActionDefinition(
        name="request_info",
        description="Request additional technical details or configuration parameters from the client before continuing testing or auditing.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={
            "ticket_id": "str",
            "info_requested": "str",
            "evidence": "str"
        },
    ),
    "close": ActionDefinition(
        name="close",
        description="Permanently close a ticket after the customer confirms the security vulnerability is resolved and fix is verified.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={
            "ticket_id": "str",
            "reason": "str",
            "evidence": "str"
        },
    ),
}



def get_action(name: str) -> ActionDefinition:
    """Retrieve an action definition. Raises KeyError if not registered."""
    if name not in REGISTRY:
        from shared.exceptions import ActionNotFoundError
        raise ActionNotFoundError(
            f"Action '{name}' is not registered.",
            details={"available": list(REGISTRY.keys())},
        )
    return REGISTRY[name]

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
    "read_ticket": ActionDefinition(
        name="read_ticket",
        description="Read a single ticket record by ID from the ticket database.",
        action_type=ActionType.READ,
        risk_level=RiskLevel.SAFE,
        requires_hitl=False,
        parameter_schema={"ticket_id": "str"},
    ),
    "read_ticket_list": ActionDefinition(
        name="read_ticket_list",
        description="List tickets filtered by status, priority, or category.",
        action_type=ActionType.READ,
        risk_level=RiskLevel.SAFE,
        requires_hitl=False,
        parameter_schema={
            "status": "str | None",
            "priority": "str | None",
            "category": "str | None",
            "limit": "int",
        },
    ),
    "write_json_file": ActionDefinition(
        name="write_json_file",
        description=(
            "Write a JSON file to the sandboxed workspace directory. "
            "Path is validated and a backup is created before writing."
        ),
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,   # Hardcoded True — never set to False
        parameter_schema={"target_path": "str", "content": "dict"},
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

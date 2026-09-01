from __future__ import annotations

from typing import Any

from src.utils.models.action import ActionDefinition, ActionType, RiskLevel

REGISTRY: dict[str, ActionDefinition] = {
    "auto_respond": ActionDefinition(
        name="auto_respond",
        description="Resolve a ticket automatically or answer a general query by sending a drafted response backed by specific knowledge chunks. Safe to execute without human approval.",
        action_type=ActionType.READ,
        risk_level=RiskLevel.SAFE,
        requires_hitl=False,
        parameter_schema={"ticket_id": "str | None", "response_text": "str", "evidence": "str"},
    ),
    "get_ticket_status": ActionDefinition(
        name="get_ticket_status",
        description="Read the current status and metadata for an existing ticket without modifying it.",
        action_type=ActionType.READ,
        risk_level=RiskLevel.SAFE,
        requires_hitl=False,
        parameter_schema={"ticket_id": "str"},
    ),
    "escalate": ActionDefinition(
        name="escalate",
        description="Escalate a ticket to senior security consultants or architects due to complexity, critical severity, or customer SLA urgency.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={"ticket_id": "str", "reason": "str", "evidence": "str"},
    ),
    "request_info": ActionDefinition(
        name="request_info",
        description="Request additional technical details or configuration parameters from the client before continuing testing or auditing.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={"ticket_id": "str", "info_requested": "str", "evidence": "str"},
    ),
    "close": ActionDefinition(
        name="close",
        description="Permanently close a ticket after the customer confirms the security vulnerability is resolved and fix is verified.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={"ticket_id": "str", "reason": "str", "evidence": "str"},
    ),
    "write_json_file": ActionDefinition(
        name="write_json_file",
        description="Write structured data as a JSON file inside the workspace sandbox.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={"target_path": "str", "content": "dict"},
    ),
    "create_ticket": ActionDefinition(
        name="create_ticket",
        description="Create a new IT or security support ticket in the ticketing system.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.SAFE,
        requires_hitl=False,
        parameter_schema={
            "user_name": "str",
            "category": "str",
            "priority": "str",
            "description": "str",
            "evidence": "str",
        },
    ),
    "quarantine_ip": ActionDefinition(
        name="quarantine_ip",
        description="Block or quarantine an external IP address on the perimeter firewall.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={
            "ip": "str",
            "reason": "str",
            "evidence": "str",
        },
    ),
    "unlock_account": ActionDefinition(
        name="unlock_account",
        description="Unlock a locked user or Active Directory account after failed login attempts.",
        action_type=ActionType.WRITE,
        risk_level=RiskLevel.CRITICAL,
        requires_hitl=True,
        parameter_schema={
            "user_email": "str",
            "reason": "str",
            "evidence": "str",
        },
    ),
}

ACTION_POLICY_METADATA: dict[str, dict[str, Any]] = {
    "create_ticket": {
        "staging_permitted_roles": ["end_user", "tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": False,
        "authorizing_roles": ["end_user", "tier1_analyst", "incident_commander", "admin"],
        "minimum_approver_clearance": "PUBLIC",
        "audit_tags": ["RBAC:TICKET_CREATION", "SYNTHETIC_ENVIRONMENT:WRITE"],
    },
    "quarantine_ip": {
        "staging_permitted_roles": ["tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": True,
        "authorizing_roles": ["incident_commander", "admin"],
        "minimum_approver_clearance": "TIER_2",
        "audit_tags": ["RBAC:FIREWALL_MUTATION", "NIST:AC-3", "GOVERNANCE:FOUR_EYES"],
    },
    "unlock_account": {
        "staging_permitted_roles": ["tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": True,
        "authorizing_roles": ["incident_commander", "admin"],
        "minimum_approver_clearance": "TIER_2",
        "audit_tags": ["RBAC:IDENTITY_MANAGEMENT", "NIST:AC-2", "GOVERNANCE:FOUR_EYES"],
    },
    "escalate": {
        "staging_permitted_roles": ["tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": True,
        "authorizing_roles": ["incident_commander", "admin"],
        "minimum_approver_clearance": "TIER_2",
        "audit_tags": ["RBAC:INCIDENT_ESCALATION", "GOVERNANCE:FOUR_EYES"],
    },
    "request_info": {
        "staging_permitted_roles": ["tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": False,
        "authorizing_roles": ["tier1_analyst", "incident_commander", "admin"],
        "minimum_approver_clearance": "TIER_1",
        "audit_tags": ["RBAC:INFO_REQUEST"],
    },
    "close": {
        "staging_permitted_roles": ["incident_commander", "admin"],
        "requires_four_eyes": True,
        "authorizing_roles": ["incident_commander", "admin"],
        "minimum_approver_clearance": "TIER_2",
        "audit_tags": ["RBAC:TICKET_CLOSURE", "GOVERNANCE:FOUR_EYES"],
    },
    "write_json_file": {
        "staging_permitted_roles": ["tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": True,
        "authorizing_roles": ["incident_commander", "admin"],
        "minimum_approver_clearance": "TIER_2",
        "audit_tags": ["SANDBOX:WRITE_FILE", "GOVERNANCE:FOUR_EYES"],
    },
    "auto_respond": {
        "staging_permitted_roles": ["end_user", "tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": False,
        "authorizing_roles": ["end_user", "tier1_analyst", "incident_commander", "admin"],
        "minimum_approver_clearance": "PUBLIC",
        "audit_tags": ["KNOWLEDGE:READ_ONLY"],
    },
    "get_ticket_status": {
        "staging_permitted_roles": ["end_user", "tier1_analyst", "incident_commander", "admin"],
        "requires_four_eyes": False,
        "authorizing_roles": ["end_user", "tier1_analyst", "incident_commander", "admin"],
        "minimum_approver_clearance": "PUBLIC",
        "audit_tags": ["TICKET:READ_ONLY"],
    },
}


def get_action(name: str) -> ActionDefinition:
    """Retrieve an action definition. Raises KeyError if not registered."""
    if name not in REGISTRY:
        from src.utils.exceptions import ActionNotFoundError

        raise ActionNotFoundError(
            f"Action '{name}' is not registered.",
            details={"available": list(REGISTRY.keys())},
        )
    return REGISTRY[name]


def get_privileged_action_terms() -> tuple[str, ...]:
    """Return operator-intent phrases derived from registered privileged actions."""
    terms: set[str] = set()
    for action in REGISTRY.values():
        if not (action.requires_hitl or action.risk_level == RiskLevel.CRITICAL):
            continue
        normalized = action.name.replace("_", " ")
        terms.add(action.name)
        terms.add(normalized)

        words = normalized.split()
        if words:
            terms.add(words[0])
        if len(words) > 1:
            terms.add(" ".join(words[:2]))

    return tuple(sorted(terms, key=lambda item: (-len(item), item)))

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from src.utils.constants import TICKET_ID_REGEX
from src.utils.registry import ACTION_POLICY_METADATA, REGISTRY

log = structlog.get_logger(__name__)

_STATUS_KEYWORDS: frozenset[str] = frozenset(
    {
        "status of",
        "ticket status",
        "check status",
        "what is the status",
    }
)


def should_override_to_auto_respond(user_message: str, proposed_action: str) -> tuple[bool, bool]:
    """
    Deterministic safety guard: prevent write actions without explicit ticket ID.
    Status queries and messages without a ticket ID must not trigger
    escalate/request_info/close actions.
    Returns (should_override, is_status_query).
    """
    if proposed_action not in ("escalate", "request_info", "close"):
        return False, False
    msg_lower = user_message.lower()
    is_status_query = any(kw in msg_lower for kw in _STATUS_KEYWORDS)
    has_ticket = bool(TICKET_ID_REGEX.search(user_message))
    should_override = is_status_query or not has_ticket
    return should_override, is_status_query


class ClearanceLevel(StrEnum):
    PUBLIC = "PUBLIC"
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    ADMIN = "ADMIN"


ROLE_CLEARANCE_MAP: dict[str, ClearanceLevel] = {
    "end_user": ClearanceLevel.PUBLIC,
    "operator": ClearanceLevel.TIER_1,
    "tier1_analyst": ClearanceLevel.TIER_1,
    "soc_tier1": ClearanceLevel.TIER_1,
    "soc_tier2": ClearanceLevel.TIER_2,
    "incident_commander": ClearanceLevel.TIER_2,
    "security_lead": ClearanceLevel.TIER_2,
    "admin": ClearanceLevel.ADMIN,
}

CLEARANCE_HIERARCHY: dict[ClearanceLevel, int] = {
    ClearanceLevel.PUBLIC: 0,
    ClearanceLevel.TIER_1: 1,
    ClearanceLevel.TIER_2: 2,
    ClearanceLevel.ADMIN: 3,
}

ROLE_ALIASES: dict[str, str] = {
    "operator": "tier1_analyst",
    "soc_tier1": "tier1_analyst",
    "soc_tier2": "incident_commander",
    "security_lead": "incident_commander",
}


def normalize_operator_role(role: str | None) -> str:
    clean_role = (role or "end_user").lower()
    return ROLE_ALIASES.get(clean_role, clean_role)


class PolicyDecision(BaseModel):
    allowed: bool = True
    action_name: str
    operator_role: str
    reason: str
    requires_four_eyes: bool = False
    minimum_approver_clearance: ClearanceLevel = ClearanceLevel.TIER_2
    authorized_approver_roles: list[str] = Field(default_factory=list)
    audit_tags: list[str] = Field(default_factory=list)


class ApprovalPolicyDecision(BaseModel):
    allowed: bool
    reason: str
    status_code: int = 200
    approver_role: str
    clearance_level: ClearanceLevel


class ActionPolicyRule(BaseModel):
    action_name: str
    description: str
    staging_permitted_roles: list[str]
    requires_four_eyes: bool
    authorizing_roles: list[str]
    minimum_approver_clearance: ClearanceLevel
    audit_tags: list[str]


def build_action_policies() -> dict[str, ActionPolicyRule]:
    """Build policy rules from the action registry and registry-owned metadata."""
    policies: dict[str, ActionPolicyRule] = {}
    for action_name, action_def in REGISTRY.items():
        metadata = ACTION_POLICY_METADATA[action_name]
        policies[action_name] = ActionPolicyRule(
            action_name=action_name,
            description=action_def.description,
            staging_permitted_roles=list(metadata["staging_permitted_roles"]),
            requires_four_eyes=bool(metadata["requires_four_eyes"]),
            authorizing_roles=list(metadata["authorizing_roles"]),
            minimum_approver_clearance=ClearanceLevel(
                str(metadata["minimum_approver_clearance"])
            ),
            audit_tags=list(metadata["audit_tags"]),
        )
    return policies


DEFAULT_ACTION_POLICIES: dict[str, ActionPolicyRule] = build_action_policies()

# Dynamic Least-Privilege Knowledge Redaction Rules
SENSITIVE_KNOWLEDGE_PATTERNS: list[tuple[re.Pattern, str, ClearanceLevel]] = [
    (
        re.compile(r"SOP-02\s*:\s*.*?(?=\n\n|\Z)", re.DOTALL | re.IGNORECASE),
        "[🔒 RESTRICTED: Forensic Runbook SOP-02 requires Tier 2+ clearance]",
        ClearanceLevel.TIER_2,
    ),
    (
        re.compile(r"(?:volatility|winpmem|dd\s+if=).*?(?=\n|\Z)", re.IGNORECASE),
        "[🔒 RESTRICTED: Memory dump command masked for current clearance]",
        ClearanceLevel.TIER_2,
    ),
    (
        re.compile(
            r"(?:api_key|token|secret)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{8,}['\"]", re.IGNORECASE
        ),
        "[🔒 REDACTED: API credential masked by Least-Privilege Policy]",
        ClearanceLevel.ADMIN,
    ),
]


class PolicyEngine:
    """Enterprise Policy-as-Code Evaluation Engine."""

    def __init__(self, policies: dict[str, ActionPolicyRule] | None = None) -> None:
        self._policies = policies or DEFAULT_ACTION_POLICIES

    def evaluate_action_staging(
        self, action_name: str, operator_role: str, payload: dict[str, Any] | None = None
    ) -> PolicyDecision:
        """Evaluate whether an operator role is permitted to initiate or stage an action."""
        clean_role = normalize_operator_role(operator_role)
        rule = self._policies.get(action_name)

        if not rule:
            log.warning("policy.unknown_action", action=action_name, role=clean_role)
            return PolicyDecision(
                allowed=False,
                action_name=action_name,
                operator_role=clean_role,
                reason=f"Action '{action_name}' is not registered in enterprise security policy.",
                audit_tags=["POLICY_VIOLATION:UNREGISTERED_ACTION"],
            )

        if clean_role not in rule.staging_permitted_roles:
            log.warning("policy.staging_denied", action=action_name, role=clean_role)
            return PolicyDecision(
                allowed=False,
                action_name=action_name,
                operator_role=clean_role,
                reason=f"Persona '{clean_role}' has insufficient clearance to initiate action '{action_name}'.",
                audit_tags=["POLICY_DENIAL:INSUFFICIENT_STAGING_CLEARANCE"],
            )

        return PolicyDecision(
            allowed=True,
            action_name=action_name,
            operator_role=clean_role,
            reason="Action staging approved under declarative RBAC policy.",
            requires_four_eyes=rule.requires_four_eyes,
            minimum_approver_clearance=rule.minimum_approver_clearance,
            authorized_approver_roles=rule.authorizing_roles,
            audit_tags=rule.audit_tags,
        )

    def evaluate_approval_decision(
        self, action_name: str, approver_role: str | None, decision: str = "approve"
    ) -> ApprovalPolicyDecision:
        """Evaluate Four-Eyes authorization decision against minimum clearance rules."""
        clean_role = normalize_operator_role(approver_role or "admin")
        clearance = ROLE_CLEARANCE_MAP.get(clean_role, ClearanceLevel.PUBLIC)

        if decision == "reject":
            return ApprovalPolicyDecision(
                allowed=True,
                reason="Operator rejected the pending execution.",
                status_code=200,
                approver_role=clean_role,
                clearance_level=clearance,
            )

        # Enforce Four-Eyes Principle for unprivileged roles unconditionally
        if clean_role in {"tier1_analyst", "end_user"}:
            return ApprovalPolicyDecision(
                allowed=False,
                reason=(
                    f"Four-Eyes Dual-Authorization Clearance Violation: Persona '{clean_role}' ({clearance.value}) "
                    f"cannot authorize critical actions. Requires Incident Commander or Admin clearance."
                ),
                status_code=403,
                approver_role=clean_role,
                clearance_level=clearance,
            )

        rule = self._policies.get(action_name)
        if not rule:
            # For unrecognized or general operational actions, approve if approver is privileged (admin/IC)
            return ApprovalPolicyDecision(
                allowed=True,
                reason=f"Four-Eyes authorization granted by {clean_role} ({clearance.value}).",
                status_code=200,
                approver_role=clean_role,
                clearance_level=clearance,
            )

        if not rule.requires_four_eyes:
            return ApprovalPolicyDecision(
                allowed=True,
                reason="Action is pre-approved for automated / single-operator execution.",
                status_code=200,
                approver_role=clean_role,
                clearance_level=clearance,
            )

        # Enforce minimum clearance level
        approver_level_int = CLEARANCE_HIERARCHY.get(clearance, 0)
        required_level_int = CLEARANCE_HIERARCHY.get(rule.minimum_approver_clearance, 2)

        if approver_level_int < required_level_int or clean_role not in rule.authorizing_roles:
            log.warning(
                "policy.four_eyes_clearance_violation",
                action=action_name,
                approver_role=clean_role,
                clearance=clearance.value,
                required_clearance=rule.minimum_approver_clearance.value,
            )
            return ApprovalPolicyDecision(
                allowed=False,
                reason=(
                    f"Four-Eyes Dual-Authorization Clearance Violation: Persona '{clean_role}' ({clearance.value}) "
                    f"cannot authorize '{action_name}'. Requires minimum {rule.minimum_approver_clearance.value} clearance "
                    f"({', '.join(rule.authorizing_roles)})."
                ),
                status_code=403,
                approver_role=clean_role,
                clearance_level=clearance,
            )

        return ApprovalPolicyDecision(
            allowed=True,
            reason=f"Four-Eyes authorization granted by {clean_role} ({clearance.value}).",
            status_code=200,
            approver_role=clean_role,
            clearance_level=clearance,
        )

    def redact_knowledge_content(self, operator_role: str, text: str) -> str:
        """Apply dynamic field-level and SOP redactions based on caller clearance."""
        if not text:
            return ""

        clean_role = normalize_operator_role(operator_role)
        caller_clearance = ROLE_CLEARANCE_MAP.get(clean_role, ClearanceLevel.PUBLIC)
        caller_level_int = CLEARANCE_HIERARCHY.get(caller_clearance, 0)

        redacted = text
        for pattern, replacement, min_required_clearance in SENSITIVE_KNOWLEDGE_PATTERNS:
            min_level_int = CLEARANCE_HIERARCHY.get(min_required_clearance, 2)
            if caller_level_int < min_level_int:
                redacted = pattern.sub(replacement, redacted)

        return redacted


# Global singleton policy engine instance
_policy_engine = PolicyEngine()


def get_policy_engine() -> PolicyEngine:
    """Return singleton PolicyEngine instance."""
    return _policy_engine

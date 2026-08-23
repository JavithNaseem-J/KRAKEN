"""
Declarative Policy-as-Code Engine (OPA/Rego-Style Architecture).

Decouples enterprise security clearance, Role-Based Access Control (RBAC),
Four-Eyes dual-authorization rules, and dynamic data leakage protection
from application business logic.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from src.utils.constants import TICKET_ID_REGEX

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
    "tier1_analyst": ClearanceLevel.TIER_1,
    "incident_commander": ClearanceLevel.TIER_2,
    "admin": ClearanceLevel.ADMIN,
}

CLEARANCE_HIERARCHY: dict[ClearanceLevel, int] = {
    ClearanceLevel.PUBLIC: 0,
    ClearanceLevel.TIER_1: 1,
    ClearanceLevel.TIER_2: 2,
    ClearanceLevel.ADMIN: 3,
}


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


# ── Declarative Policy Rules Matrix ───────────────────────────────────────────
DEFAULT_ACTION_POLICIES: dict[str, ActionPolicyRule] = {
    "create_ticket": ActionPolicyRule(
        action_name="create_ticket",
        description="Stage and create a new IT or security support ticket.",
        staging_permitted_roles=["end_user", "tier1_analyst", "incident_commander", "admin"],
        requires_four_eyes=True,
        authorizing_roles=["incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.TIER_2,
        audit_tags=["RBAC:TICKET_CREATION", "GOVERNANCE:FOUR_EYES"],
    ),
    "quarantine_ip": ActionPolicyRule(
        action_name="quarantine_ip",
        description="Block external IP on perimeter firewall ruleset.",
        staging_permitted_roles=["tier1_analyst", "incident_commander", "admin"],
        requires_four_eyes=True,
        authorizing_roles=["incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.TIER_2,
        audit_tags=["RBAC:FIREWALL_MUTATION", "NIST:AC-3", "GOVERNANCE:FOUR_EYES"],
    ),
    "unlock_account": ActionPolicyRule(
        action_name="unlock_account",
        description="Clear Active Directory / Microsoft Graph account lockout.",
        staging_permitted_roles=["tier1_analyst", "incident_commander", "admin"],
        requires_four_eyes=True,
        authorizing_roles=["incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.TIER_2,
        audit_tags=["RBAC:IDENTITY_MANAGEMENT", "NIST:AC-2", "GOVERNANCE:FOUR_EYES"],
    ),
    "escalate": ActionPolicyRule(
        action_name="escalate",
        description="Escalate high-severity incident ticket to emergency engineering.",
        staging_permitted_roles=["tier1_analyst", "incident_commander", "admin"],
        requires_four_eyes=True,
        authorizing_roles=["incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.TIER_2,
        audit_tags=["RBAC:INCIDENT_ESCALATION", "GOVERNANCE:FOUR_EYES"],
    ),
    "request_info": ActionPolicyRule(
        action_name="request_info",
        description="Request supplemental details from ticket requester.",
        staging_permitted_roles=["tier1_analyst", "incident_commander", "admin"],
        requires_four_eyes=False,
        authorizing_roles=["tier1_analyst", "incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.TIER_1,
        audit_tags=["RBAC:INFO_REQUEST"],
    ),
    "close": ActionPolicyRule(
        action_name="close",
        description="Mark verified incident ticket resolved and closed.",
        staging_permitted_roles=["incident_commander", "admin"],
        requires_four_eyes=True,
        authorizing_roles=["incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.TIER_2,
        audit_tags=["RBAC:TICKET_CLOSURE", "GOVERNANCE:FOUR_EYES"],
    ),
    "write_json_file": ActionPolicyRule(
        action_name="write_json_file",
        description="Write structured report to local sandbox.",
        staging_permitted_roles=["tier1_analyst", "incident_commander", "admin"],
        requires_four_eyes=True,
        authorizing_roles=["incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.TIER_2,
        audit_tags=["SANDBOX:WRITE_FILE", "GOVERNANCE:FOUR_EYES"],
    ),
    "auto_respond": ActionPolicyRule(
        action_name="auto_respond",
        description="Automated knowledge base Q&A and status reporting.",
        staging_permitted_roles=["end_user", "tier1_analyst", "incident_commander", "admin"],
        requires_four_eyes=False,
        authorizing_roles=["end_user", "tier1_analyst", "incident_commander", "admin"],
        minimum_approver_clearance=ClearanceLevel.PUBLIC,
        audit_tags=["KNOWLEDGE:READ_ONLY"],
    ),
}

# ── Dynamic Least-Privilege Knowledge Redaction Rules ─────────────────────────
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
        clean_role = (operator_role or "end_user").lower()
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
        clean_role = (approver_role or "admin").lower()
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

        clean_role = (operator_role or "end_user").lower()
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

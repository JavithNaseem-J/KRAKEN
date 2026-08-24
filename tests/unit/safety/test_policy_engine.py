from src.safety.policy_engine import (
    DEFAULT_ACTION_POLICIES,
    ROLE_CLEARANCE_MAP,
    ClearanceLevel,
    get_policy_engine,
)
from src.utils.registry import ACTION_POLICY_METADATA, REGISTRY


def test_role_clearance_mapping():
    """Verify role-to-clearance level hierarchy."""
    assert ROLE_CLEARANCE_MAP["end_user"] == ClearanceLevel.PUBLIC
    assert ROLE_CLEARANCE_MAP["tier1_analyst"] == ClearanceLevel.TIER_1
    assert ROLE_CLEARANCE_MAP["incident_commander"] == ClearanceLevel.TIER_2
    assert ROLE_CLEARANCE_MAP["admin"] == ClearanceLevel.ADMIN


def test_action_staging_evaluation():
    """Verify role permissions for action staging."""
    engine = get_policy_engine()

    # End user can stage ticket creation
    dec = engine.evaluate_action_staging("create_ticket", "end_user")
    assert dec.allowed is True
    assert dec.requires_four_eyes is True

    # End user CANNOT stage perimeter IP quarantine
    dec = engine.evaluate_action_staging("quarantine_ip", "end_user")
    assert dec.allowed is False
    assert "insufficient clearance" in dec.reason.lower()

    # Tier 1 analyst can stage IP quarantine
    dec = engine.evaluate_action_staging("quarantine_ip", "tier1_analyst")
    assert dec.allowed is True
    assert dec.requires_four_eyes is True
    assert "incident_commander" in dec.authorized_approver_roles

    # Generic gateway operator header maps to Tier 1 staging permissions.
    dec = engine.evaluate_action_staging("escalate", "operator")
    assert dec.allowed is True
    assert dec.operator_role == "tier1_analyst"


def test_action_registry_and_policy_metadata_are_one_to_one():
    assert set(ACTION_POLICY_METADATA) == set(REGISTRY)
    assert set(DEFAULT_ACTION_POLICIES) == set(REGISTRY)

    for name, policy in DEFAULT_ACTION_POLICIES.items():
        assert policy.action_name == name
        assert policy.description == REGISTRY[name].description


def test_four_eyes_clearance_evaluation():
    """Verify Four-Eyes dual-authorization approval evaluation."""
    engine = get_policy_engine()

    # Tier 1 analyst cannot authorize critical operational actions
    eval_tier1 = engine.evaluate_approval_decision("quarantine_ip", "tier1_analyst", decision="approve")
    assert eval_tier1.allowed is False
    assert eval_tier1.status_code == 403
    assert "Clearance Violation" in eval_tier1.reason

    # End user cannot authorize operational actions
    eval_user = engine.evaluate_approval_decision("unlock_account", "end_user", decision="approve")
    assert eval_user.allowed is False
    assert eval_user.status_code == 403

    # Incident Commander can authorize IP quarantine and account unlock
    eval_ic = engine.evaluate_approval_decision("quarantine_ip", "incident_commander", decision="approve")
    assert eval_ic.allowed is True
    assert eval_ic.status_code == 200

    # Admin can authorize any action
    eval_admin = engine.evaluate_approval_decision("unlock_account", "admin", decision="approve")
    assert eval_admin.allowed is True
    assert eval_admin.status_code == 200

    # Rejections are always allowed regardless of role
    eval_reject = engine.evaluate_approval_decision("quarantine_ip", "tier1_analyst", decision="reject")
    assert eval_reject.allowed is True


def test_dynamic_knowledge_redaction():
    """Verify dynamic SOP and credential redactions by caller clearance."""
    engine = get_policy_engine()
    raw_sop = "SOP-02: Run volatility script winpmem.exe to extract RAM dump. api_key='sk-test-secret-12345'"

    # End user sees full redaction
    redacted_user = engine.redact_knowledge_content("end_user", raw_sop)
    assert "[🔒 RESTRICTED" in redacted_user or "[🔒 REDACTED" in redacted_user
    assert "sk-test-secret-12345" not in redacted_user

    # Tier 1 analyst sees SOP redacted
    redacted_tier1 = engine.redact_knowledge_content("tier1_analyst", raw_sop)
    assert "[🔒 RESTRICTED" in redacted_tier1 or "[🔒 REDACTED" in redacted_tier1

    # Incident Commander sees SOP but API credentials redacted
    redacted_ic = engine.redact_knowledge_content("incident_commander", raw_sop)
    assert "sk-test-secret-12345" not in redacted_ic

    # Admin sees unredacted text
    admin_text = engine.redact_knowledge_content("admin", raw_sop)
    assert "winpmem.exe" in admin_text

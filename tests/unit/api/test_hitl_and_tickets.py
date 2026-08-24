from src.tools.ticket import quarantine_ip_handler, unlock_account_handler
from src.utils.registry import REGISTRY, get_action


def test_registry_has_operational_actions():
    """Verify quarantine_ip and unlock_account are registered as CRITICAL HITL actions."""
    assert "quarantine_ip" in REGISTRY
    assert "unlock_account" in REGISTRY

    q_action = get_action("quarantine_ip")
    assert q_action.requires_hitl is True
    assert q_action.risk_level.value == "CRITICAL"

    u_action = get_action("unlock_account")
    assert u_action.requires_hitl is True
    assert u_action.risk_level.value == "CRITICAL"


def test_quarantine_ip_handler():
    """Verify quarantine_ip_handler returns an explicit dry-run receipt."""
    res = quarantine_ip_handler("198.51.100.45", reason="Port scanning detected")
    assert res["success"] is True
    assert res["mode"] == "dry_run"
    assert res["simulated"] is True
    assert res["status"] == "would_block"
    assert res["ip"] == "198.51.100.45"
    assert "DENY_PERIMETER_198.51.100.45" in res["firewall_rule"]
    assert "transaction_id" in res
    assert "job_id" in res
    assert "DRY_RUN_ONLY" in res["verification_status"]
    assert "no perimeter firewall rule was created" in res["message"]


def test_unlock_account_handler():
    """Verify unlock_account_handler returns an explicit dry-run receipt."""
    res = unlock_account_handler("alice.smith@company.com", reason="Identity verified")
    assert res["success"] is True
    assert res["mode"] == "dry_run"
    assert res["simulated"] is True
    assert res["status"] == "would_unlock"
    assert res["user_email"] == "alice.smith@company.com"
    assert "transaction_id" in res
    assert res["lockout_cleared"] is False
    assert "DRY_RUN_ONLY" in res["verification_status"]
    assert "no Microsoft Graph API mutation was sent" in res["message"]

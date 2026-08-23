from src.tools.ticket import get_ticket_by_id, quarantine_ip_handler, unlock_account_handler
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
    """Verify quarantine_ip_handler execution with receipt."""
    res = quarantine_ip_handler("198.51.100.45", reason="Port scanning detected")
    assert res["success"] is True
    assert res["status"] == "blocked"
    assert res["ip"] == "198.51.100.45"
    assert "DENY_PERIMETER_198.51.100.45" in res["firewall_rule"]
    assert "transaction_id" in res
    assert "job_id" in res
    assert "RECONCILED" in res["verification_status"]


def test_unlock_account_handler():
    """Verify unlock_account_handler execution with receipt."""
    res = unlock_account_handler("alice.smith@company.com", reason="Identity verified")
    assert res["success"] is True
    assert res["status"] == "unlocked"
    assert res["user_email"] == "alice.smith@company.com"
    assert "transaction_id" in res
    assert res["lockout_cleared"] is True
    assert "RECONCILED" in res["verification_status"]


def test_get_ticket_by_id_seeded_fallback():
    """Verify get_ticket_by_id retrieves ticket details from PostgreSQL/seed with alias tolerance."""
    for query_id in ("TCK-1001", "T-1001", "tck-1001", "1001"):
        ticket = get_ticket_by_id(query_id)
        assert ticket is not None, f"Failed to retrieve ticket for query_id={query_id}"
        t_id = ticket.get("id") or ticket.get("ticket_id")
        assert "1001" in str(t_id)



import pytest

from src.client.sdk import KrakenClient, kraken_sdk


def test_kraken_sdk_initialization():
    """Verify KrakenClient initializes all typed subservice clients."""
    client = KrakenClient()
    assert client.approval is not None
    assert client.action is not None
    assert client.knowledge is not None


@pytest.mark.asyncio
async def test_sdk_action_client_execution():
    """Verify typed action client executes actions and parses response DTO."""
    res = await kraken_sdk.action.execute_action(
        action_name="quarantine_ip",
        payload={"ip": "198.51.100.99", "reason": "Automated security test"},
        session_id="sdk-test-session",
        user_id="demo-user-1",
    )
    assert res.success is True
    assert res.action == "quarantine_ip"
    assert res.result is not None
    assert res.result.get("ip") == "198.51.100.99"


@pytest.mark.asyncio
async def test_sdk_approval_client_lifecycle():
    """Verify approval client enqueues, fetches details, and submits decisions."""
    # 1. Enqueue
    reg = await kraken_sdk.approval.create_pending(
        action_name="unlock_account",
        payload={"user_email": "user.test@company.com"},
        reasoning="Password reset lockout",
        session_id="sdk-approval-test-session",
    )
    assert reg.approval_id is not None
    assert len(reg.approval_id) > 10

    # 2. Get Details
    details = await kraken_sdk.approval.get_details(reg.approval_id)
    assert details.approval_id is not None
    assert details.action_name in {"unlock_account", "write_json_file"}
    assert details.csrf_token != ""

    # 3. Four-Eyes Rejection by Tier 1 analyst should be blocked under policy
    with pytest.raises(Exception, match=r".+"):
        await kraken_sdk.approval.submit_decision(
            approval_id=reg.approval_id,
            decision="approve",
            csrf_token=details.csrf_token,
            approver_role="tier1_analyst",
        )

    # 4. Valid Approval by Admin with fresh CSRF token
    details_fresh = await kraken_sdk.approval.get_details(reg.approval_id)
    decision_res = await kraken_sdk.approval.submit_decision(
        approval_id=reg.approval_id,
        decision="approve",
        csrf_token=details_fresh.csrf_token,
        approver_role="admin",
    )
    assert decision_res is not None

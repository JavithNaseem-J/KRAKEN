from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import fakeredis.aioredis
import pytest

from src.utils.approval.queue import ApprovalQueue


@pytest.mark.asyncio
async def test_resolved_stable_approval_cannot_be_reenqueued() -> None:
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = fakeredis.aioredis.FakeRedis(
        server=fakeredis.FakeServer(), decode_responses=True
    )
    approval_id = "stable-approval-id"
    request = {
        "action_name": "quarantine_ip",
        "payload": {
            "ip": "203.0.113.10",
            "context": {"reasoning": "private model analysis"},
        },
        "session_id": "northstar-v1_public-session",
        "initiator_id": "alice",
        "initiator_role": "tier1_analyst",
        "approval_id": approval_id,
    }

    assert await queue.enqueue(**request) == approval_id
    pending = await queue.get(approval_id)
    assert pending is not None
    assert "reasoning" not in str(pending).lower()
    assert pending["payload"]["ip"] == "203.0.113.10"
    assert await queue.resolve(approval_id) is not None

    assert await queue.enqueue(**request) == approval_id
    assert await queue.get(approval_id) is None
    assert await queue.stats() == 0
    await queue.close()


@pytest.mark.asyncio
async def test_decision_is_retained_and_execution_is_claimed_once() -> None:
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = fakeredis.aioredis.FakeRedis(
        server=fakeredis.FakeServer(), decode_responses=True
    )
    approval_id = await queue.enqueue(
        action_name="quarantine_ip",
        payload={"ip": "203.0.113.10"},
        session_id="session-1",
        public_session_id="visitor-1",
        initiator_id="alice",
        approval_id="decision-1",
    )
    await queue.resolve(
        approval_id,
        decision="approve",
        approver_id="bob",
        approver_role="incident_commander",
    )
    decision = await queue.get_decision(approval_id)
    assert decision is not None
    assert decision["decision"] == "approve"
    assert decision["payload"] == {"ip": "203.0.113.10"}
    assert decision["public_session_id"] == "visitor-1"
    assert decision["approver_id"] == "bob"

    assert await queue.claim_execution(approval_id) == ("claimed", None)
    assert await queue.claim_execution(approval_id) == ("in_progress", None)
    await queue.complete_execution(approval_id, {"action_name": "quarantine_ip", "success": True})
    assert await queue.claim_execution(approval_id) == (
        "complete",
        {"action_name": "quarantine_ip", "success": True},
    )
    await queue.close()


@pytest.mark.asyncio
async def test_concurrent_claim_and_uncertain_result_never_reexecute() -> None:
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = fakeredis.aioredis.FakeRedis(
        server=fakeredis.FakeServer(), decode_responses=True
    )
    claims = await asyncio.gather(*(queue.claim_execution("uncertain-1") for _ in range(10)))
    assert [status for status, _ in claims].count("claimed") == 1
    assert [status for status, _ in claims].count("in_progress") == 9
    assert await queue.claim_execution("uncertain-1") == ("in_progress", None)
    await queue.close()


@pytest.mark.asyncio
async def test_legacy_reasoning_entries_are_purged() -> None:
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = fakeredis.aioredis.FakeRedis(
        server=fakeredis.FakeServer(), decode_responses=True
    )
    await queue._redis.set(
        f"{queue._prefix}legacy-id",
        '{"approval_id":"legacy-id","reasoning":"private analysis"}',
    )
    await queue._redis.sadd(queue._index, "legacy-id")

    assert await queue.purge_legacy_reasoning_entries() == 1
    assert await queue._redis.get(f"{queue._prefix}legacy-id") is None
    assert await queue.stats() == 0
    await queue.close()


@pytest.mark.asyncio
async def test_expired_in_memory_approval_cannot_be_resolved() -> None:
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = AsyncMock()
    queue._redis.pipeline = MagicMock(side_effect=ConnectionError("Redis unavailable"))
    approval_id = "expired-approval"
    queue._in_memory_map[approval_id] = {
        "approval_id": approval_id,
        "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    queue._in_memory_csrf[approval_id] = "expired-token"

    assert await queue.resolve(approval_id) is None
    assert approval_id not in queue._in_memory_map
    assert approval_id not in queue._in_memory_csrf

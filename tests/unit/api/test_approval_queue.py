from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

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
        "session_id": "demo-session",
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
async def test_legacy_reasoning_entries_are_purged() -> None:
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = fakeredis.aioredis.FakeRedis(
        server=fakeredis.FakeServer(), decode_responses=True
    )
    await queue._redis.set(
        "kraken:approval:legacy-id",
        '{"approval_id":"legacy-id","reasoning":"private analysis"}',
    )
    await queue._redis.sadd("kraken:approval:index", "legacy-id")

    assert await queue.purge_legacy_reasoning_entries() == 1
    assert await queue._redis.get("kraken:approval:legacy-id") is None
    assert await queue.stats() == 0
    await queue.close()


@pytest.mark.asyncio
async def test_expired_in_memory_approval_cannot_be_resolved() -> None:
    queue = ApprovalQueue("redis://unused", timeout_seconds=60)
    queue._redis = AsyncMock()
    queue._redis.getdel.return_value = None
    approval_id = "expired-approval"
    queue._in_memory_map[approval_id] = {
        "approval_id": approval_id,
        "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    queue._in_memory_csrf[approval_id] = "expired-token"

    assert await queue.resolve(approval_id) is None
    assert approval_id not in queue._in_memory_map
    assert approval_id not in queue._in_memory_csrf

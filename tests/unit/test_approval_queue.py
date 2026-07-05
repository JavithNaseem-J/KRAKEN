"""
Unit tests for the ApprovalQueue.
Uses fakeredis for an in-memory Redis implementation — zero real Redis dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

# fakeredis provides an in-memory async Redis for testing
try:
    import fakeredis.aioredis as fakeredis

    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False

from services.approval.queue import ApprovalQueue

pytestmark = pytest.mark.skipif(
    not HAS_FAKEREDIS,
    reason="fakeredis not installed — run: pip install fakeredis",
)


@pytest_asyncio.fixture
async def queue() -> ApprovalQueue:
    """Return an ApprovalQueue backed by an in-memory fakeredis server."""
    q = ApprovalQueue.__new__(ApprovalQueue)
    q._redis = fakeredis.FakeRedis(decode_responses=True)
    q._timeout = 900
    return q


class TestEnqueue:
    async def test_returns_approval_id(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {"f": "v"}, "test reason", "s1")
        assert aid and len(aid) == 36  # UUID4 format

    async def test_entry_retrievable(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {"x": 1}, "r", "s1")
        entry = await queue.get(aid)
        assert entry is not None
        assert entry["action_name"] == "write_json_file"
        assert entry["session_id"] == "s1"
        assert entry["status"] == "pending"

    async def test_expires_at_in_future(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {}, "r", "s1")
        entry = await queue.get(aid)
        expires = datetime.fromisoformat(entry["expires_at"])
        assert expires > datetime.now(UTC)

    async def test_stats_and_ping(self, queue: ApprovalQueue) -> None:
        assert await queue.ping() is True
        assert await queue.stats() == 0
        await queue.enqueue("write_json_file", {}, "r", "s1")
        assert await queue.stats() == 1


class TestResolve:
    async def test_resolve_returns_entry(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {}, "r", "s1")
        entry = await queue.resolve(aid)
        assert entry is not None
        assert entry["approval_id"] == aid

    async def test_resolve_removes_from_queue(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {}, "r", "s1")
        await queue.resolve(aid)
        assert await queue.get(aid) is None
        # Verify metadata is also deleted
        assert await queue._redis.get(f"akea:approval:meta:{aid}") is None
        assert await queue.stats() == 0

    async def test_double_resolve_returns_none(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {}, "r", "s1")
        await queue.resolve(aid)
        result = await queue.resolve(aid)
        assert result is None

    async def test_resolve_unknown_id_returns_none(self, queue: ApprovalQueue) -> None:
        result = await queue.resolve("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestGetExpired:
    async def test_no_expired_initially(self, queue: ApprovalQueue) -> None:
        await queue.enqueue("write_json_file", {}, "r", "s1")
        expired = await queue.get_expired()
        assert expired == []

    async def test_detects_past_expires_at(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {}, "r", "s1")

        # Modify expires_at manually to be in the past
        entry = await queue.get(aid)
        entry["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

        await queue._redis.set(f"akea:approval:{aid}", json_dumps_compat(entry))
        await queue._redis.set(f"akea:approval:meta:{aid}", json_dumps_compat(entry))

        expired = await queue.get_expired()
        assert any(e.get("approval_id") == aid for e in expired)
        assert any(e.get("session_id") == "s1" for e in expired)

    async def test_detects_missing_main_key_with_shadow_meta(self, queue: ApprovalQueue) -> None:
        """When the main key expires, metadata shadow key must be used to get session_id."""
        aid = await queue.enqueue("write_json_file", {}, "r", "s-shadow-1")

        # Delete the main key (simulating Redis TTL expiry)
        await queue._redis.delete(f"akea:approval:{aid}")

        expired = await queue.get_expired()
        assert len(expired) == 1
        assert expired[0]["approval_id"] == aid
        assert expired[0]["session_id"] == "s-shadow-1"

        # Ensure cleanup occurred
        assert await queue._redis.get(f"akea:approval:meta:{aid}") is None
        assert await queue.stats() == 0


def json_dumps_compat(data: dict) -> str:
    import json

    return json.dumps(data)

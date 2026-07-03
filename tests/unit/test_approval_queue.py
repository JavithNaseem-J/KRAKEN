"""
Unit tests for the ApprovalQueue.
Uses fakeredis for an in-memory Redis implementation — zero real Redis dependency.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

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
    q._redis   = fakeredis.FakeRedis(decode_responses=True)
    q._timeout = 900
    return q


class TestEnqueue:
    async def test_returns_approval_id(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {"f": "v"}, "test reason", "s1")
        assert aid and len(aid) == 36  # UUID4 format

    async def test_entry_retrievable(self, queue: ApprovalQueue) -> None:
        aid   = await queue.enqueue("write_json_file", {"x": 1}, "r", "s1")
        entry = await queue.get(aid)
        assert entry is not None
        assert entry["action_name"] == "write_json_file"
        assert entry["session_id"]  == "s1"
        assert entry["status"]      == "pending"

    async def test_expires_at_in_future(self, queue: ApprovalQueue) -> None:
        aid   = await queue.enqueue("write_json_file", {}, "r", "s1")
        entry = await queue.get(aid)
        expires = datetime.fromisoformat(entry["expires_at"])
        assert expires > datetime.now(timezone.utc)


class TestResolve:
    async def test_resolve_returns_entry(self, queue: ApprovalQueue) -> None:
        aid   = await queue.enqueue("write_json_file", {}, "r", "s1")
        entry = await queue.resolve(aid)
        assert entry is not None
        assert entry["approval_id"] == aid

    async def test_resolve_removes_from_queue(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {}, "r", "s1")
        await queue.resolve(aid)
        assert await queue.get(aid) is None

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
        """Manually inject an entry with an already-past expires_at."""
        import json, uuid
        aid = str(uuid.uuid4())
        entry = {
            "approval_id": aid,
            "action_name": "write_json_file",
            "payload":     {},
            "reasoning":   "r",
            "session_id":  "s1",
            "expires_at":  (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "status":      "pending",
        }
        await queue._redis.set(f"akea:approval:{aid}", json.dumps(entry))
        await queue._redis.sadd("akea:approval:index", aid)

        expired = await queue.get_expired()
        assert any(e.get("approval_id") == aid for e in expired)

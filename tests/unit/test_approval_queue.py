"""
Unit tests for the ApprovalQueue.
Uses fakeredis for an in-memory Redis implementation — zero real Redis dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
        assert await queue._redis.get(f"kraken:approval:meta:{aid}") is None
        assert await queue.stats() == 0

    async def test_double_resolve_returns_none(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("write_json_file", {}, "r", "s1")
        await queue.resolve(aid)
        result = await queue.resolve(aid)
        assert result is None

    async def test_resolve_unknown_id_returns_none(self, queue: ApprovalQueue) -> None:
        result = await queue.resolve("00000000-0000-0000-0000-000000000000")
        assert result is None


class TestCSRFToken:
    async def test_valid_csrf_token_verifies(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("escalate", {}, "r", "s1")
        await queue.set_csrf_token(aid, "tok-abc")
        assert await queue.verify_csrf_token(aid, "tok-abc") is True

    async def test_csrf_token_consumed_after_verify(self, queue: ApprovalQueue) -> None:
        """Token must be single-use: a second submission within the TTL window is rejected."""
        aid = await queue.enqueue("escalate", {}, "r", "s1")
        await queue.set_csrf_token(aid, "tok-abc")

        # First verification succeeds and consumes the token
        first = await queue.verify_csrf_token(aid, "tok-abc")
        assert first is True

        # Second verification with the SAME token must fail (token was deleted by getdel)
        second = await queue.verify_csrf_token(aid, "tok-abc")
        assert second is False

    async def test_wrong_csrf_token_rejected(self, queue: ApprovalQueue) -> None:
        aid = await queue.enqueue("escalate", {}, "r", "s1")
        await queue.set_csrf_token(aid, "tok-correct")
        assert await queue.verify_csrf_token(aid, "tok-wrong") is False

    async def test_missing_csrf_token_fails_closed(self, queue: ApprovalQueue) -> None:
        """Verification fails closed when no token was ever set."""
        result = await queue.verify_csrf_token("nonexistent-id", "any-token")
        assert result is False

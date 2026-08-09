"""
Unit tests for the short-term session memory.
Uses fakeredis — zero real Redis dependency.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

try:
    import fakeredis.aioredis as fakeredis

    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False

from services.memory.short_term import _SESSION_TTL_SEC, ShortTermMemory

pytestmark = pytest.mark.skipif(
    not HAS_FAKEREDIS,
    reason="fakeredis not installed — run: pip install fakeredis",
)


@pytest_asyncio.fixture
async def memory() -> ShortTermMemory:
    mem = ShortTermMemory.__new__(ShortTermMemory)
    mem._redis = fakeredis.FakeRedis(decode_responses=True)
    return mem


MSGS = [
    {"role": "user", "content": "What is the SLA for critical tickets?"},
    {"role": "assistant", "content": "Critical tickets have a 1-hour response time."},
]


class TestPing:
    async def test_ping_returns_true(self, memory: ShortTermMemory) -> None:
        result = await memory.ping()
        assert result is True


class TestGetSession:
    async def test_empty_session_returns_list(self, memory: ShortTermMemory) -> None:
        result = await memory.get_session("new-session")
        assert result == []

    async def test_corrupt_value_returns_empty(self, memory: ShortTermMemory) -> None:
        await memory._redis.set("kraken:session:bad", "NOT JSON")
        result = await memory.get_session("bad")
        assert result == []


class TestUpdateSession:
    async def test_stores_and_retrieves(self, memory: ShortTermMemory) -> None:
        await memory.update_session("s1", MSGS)
        result = await memory.get_session("s1")
        assert result == MSGS

    async def test_replaces_on_second_call(self, memory: ShortTermMemory) -> None:
        await memory.update_session("s1", MSGS)
        new_msg = [{"role": "user", "content": "New question"}]
        await memory.update_session("s1", new_msg)
        result = await memory.get_session("s1")
        assert result == new_msg

    async def test_ttl_is_set(self, memory: ShortTermMemory) -> None:
        """Verify that update_session sets a TTL on the Redis key."""
        await memory.update_session("s1", MSGS)
        ttl = await memory._redis.ttl("kraken:session:s1")
        # TTL should be close to _SESSION_TTL_SEC (within 5 seconds of tolerance)
        assert _SESSION_TTL_SEC - 5 <= ttl <= _SESSION_TTL_SEC


class TestAppendMessages:
    async def test_appends_to_empty(self, memory: ShortTermMemory) -> None:
        result = await memory.append_messages("s1", MSGS)
        assert len(result) == 2

    async def test_appends_to_existing(self, memory: ShortTermMemory) -> None:
        await memory.update_session("s1", MSGS)
        extra = [{"role": "user", "content": "Follow-up"}]
        result = await memory.append_messages("s1", extra)
        assert len(result) == 3
        assert result[-1] == extra[0]

    async def test_order_preserved(self, memory: ShortTermMemory) -> None:
        await memory.update_session("s1", MSGS)
        extra = [{"role": "user", "content": "Extra"}]
        result = await memory.append_messages("s1", extra)
        assert result[:2] == MSGS

    async def test_append_is_atomic_no_data_loss(self, memory: ShortTermMemory) -> None:
        """
        Simulate a scenario where append_messages starts with an existing session
        and correctly accumulates all messages sequentially.
        """
        await memory.update_session("s1", MSGS)
        batch1 = [{"role": "user", "content": "Q1"}]
        batch2 = [{"role": "user", "content": "Q2"}]

        await memory.append_messages("s1", batch1)
        result2 = await memory.append_messages("s1", batch2)

        assert len(result2) == len(MSGS) + 2
        assert result2[-2] == batch1[0]
        assert result2[-1] == batch2[0]


class TestClearSession:
    async def test_clears_session(self, memory: ShortTermMemory) -> None:
        await memory.update_session("s1", MSGS)
        await memory.clear_session("s1")
        result = await memory.get_session("s1")
        assert result == []

    async def test_clear_nonexistent_no_error(self, memory: ShortTermMemory) -> None:
        await memory.clear_session("does-not-exist")  # should not raise

"""
Redis-backed approval queue with TTL and timeout tracking.

Key design decisions:
  - Each pending approval is stored as `akea:approval:{approval_id}` in Redis
    with a TTL equal to APPROVAL_TIMEOUT_SECONDS.
  - When Redis expires the key, the approval is implicitly gone — the background
    timeout checker detects this via a separate index key and sends a callback.
  - Index key `akea:approval:index` is a Redis Set of all active approval_ids,
    used by the timeout checker to find expired entries without scanning all keys.
  - All operations are async (redis.asyncio) — no blocking calls in the event loop.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

_PREFIX  = "akea:approval:"
_INDEX   = "akea:approval:index"


class ApprovalQueue:
    """
    Manages pending HITL approval requests in Redis.
    One instance per service process, created in lifespan().
    """

    def __init__(self, redis_url: str, timeout_seconds: int = 900) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        self._timeout = timeout_seconds

    # ── Public API ────────────────────────────────────────────────────────────

    async def enqueue(
        self,
        action_name: str,
        payload: dict[str, Any],
        reasoning: str,
        session_id: str,
    ) -> str:
        """
        Register a new pending approval. Returns the approval_id.
        Entry expires automatically after timeout_seconds via Redis TTL.
        """
        approval_id = str(uuid.uuid4())
        expires_at  = (
            datetime.now(timezone.utc) + timedelta(seconds=self._timeout)
        ).isoformat()

        entry = {
            "approval_id": approval_id,
            "action_name": action_name,
            "payload":     payload,
            "reasoning":   reasoning,
            "session_id":  session_id,
            "expires_at":  expires_at,
            "status":      "pending",
        }

        key = f"{_PREFIX}{approval_id}"
        pipe = self._redis.pipeline()
        pipe.setex(key, self._timeout, json.dumps(entry))
        pipe.sadd(_INDEX, approval_id)
        pipe.expire(_INDEX, self._timeout + 60)   # Index TTL slightly longer
        await pipe.execute()

        log.info("queue.enqueued", approval_id=approval_id, expires_at=expires_at)
        return approval_id

    async def get(self, approval_id: str) -> dict[str, Any] | None:
        """Return the pending entry, or None if expired/not found."""
        data = await self._redis.get(f"{_PREFIX}{approval_id}")
        return json.loads(data) if data else None

    async def resolve(self, approval_id: str) -> dict[str, Any] | None:
        """
        Remove an approval from the queue and return its data.
        Returns None if already resolved or expired.
        """
        key  = f"{_PREFIX}{approval_id}"
        data = await self._redis.get(key)
        if data is None:
            return None

        pipe = self._redis.pipeline()
        pipe.delete(key)
        pipe.srem(_INDEX, approval_id)
        await pipe.execute()

        log.info("queue.resolved", approval_id=approval_id)
        return json.loads(data)

    async def get_expired(self) -> list[dict[str, Any]]:
        """
        Return all entries in the index that are no longer in Redis
        (i.e., their TTL has expired). Used by the timeout checker.
        """
        all_ids = await self._redis.smembers(_INDEX)
        expired: list[dict[str, Any]] = []

        for approval_id in all_ids:
            key  = f"{_PREFIX}{approval_id}"
            data = await self._redis.get(key)
            if data is None:
                # Key expired — clean up index and report
                await self._redis.srem(_INDEX, approval_id)
                expired.append({"approval_id": approval_id})
            else:
                # Check explicit expires_at (belt-and-suspenders)
                entry      = json.loads(data)
                expires_at = datetime.fromisoformat(entry["expires_at"])
                if datetime.now(timezone.utc) >= expires_at:
                    await self.resolve(approval_id)
                    expired.append(entry)

        return expired

    async def close(self) -> None:
        await self._redis.aclose()

"""
Redis-backed approval queue with TTL and timeout tracking.

Key design decisions:
  - Each pending approval is stored as `akea:approval:{approval_id}` in Redis
    with a TTL equal to APPROVAL_TIMEOUT_SECONDS.
  - A shadow metadata key `akea:approval:meta:{approval_id}` is stored with a
    longer TTL (timeout + 1 hour) so that the background timeout checker can
    retrieve the full payload and session_id even after the main key expires.
  - Uses atomic GETDEL to eliminate double-resolve race conditions.
  - Pipelines all checks to prevent O(N) Redis round-trip overhead.
  - All operations are async (redis.asyncio) — no blocking calls in the event loop.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

_PREFIX = "akea:approval:"
_META_PREFIX = "akea:approval:meta:"
_INDEX = "akea:approval:index"


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

    async def ping(self) -> bool:
        """Ping Redis to verify connection health."""
        try:
            await self._redis.ping()
            return True
        except Exception as exc:
            log.error("queue.redis_ping_failed", error=str(exc))
            return False

    async def stats(self) -> int:
        """Return the count of pending approvals in the index."""
        return await self._redis.scard(_INDEX)

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
        A copy of the data is kept in a metadata shadow key with a longer TTL
        so we can recover the session_id on expiry.
        """
        approval_id = str(uuid.uuid4())
        expires_at = (datetime.now(UTC) + timedelta(seconds=self._timeout)).isoformat()

        entry = {
            "approval_id": approval_id,
            "action_name": action_name,
            "payload": payload,
            "reasoning": reasoning,
            "session_id": session_id,
            "expires_at": expires_at,
            "status": "pending",
        }

        key = f"{_PREFIX}{approval_id}"
        meta_key = f"{_META_PREFIX}{approval_id}"

        pipe = self._redis.pipeline()
        # Set keys without using deprecated setex
        pipe.set(key, json.dumps(entry), ex=self._timeout)
        pipe.set(meta_key, json.dumps(entry), ex=self._timeout + 3600)
        pipe.sadd(_INDEX, approval_id)
        pipe.expire(_INDEX, self._timeout + 3600)  # Keep index alive along with metadata
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
        Uses atomic GETDEL to prevent race conditions.
        """
        key = f"{_PREFIX}{approval_id}"
        meta_key = f"{_META_PREFIX}{approval_id}"

        # Atomically retrieve and delete key
        data = await self._redis.getdel(key)
        if data is None:
            return None

        # Clean up shadow meta key and index in background pipeline
        pipe = self._redis.pipeline()
        pipe.delete(meta_key)
        pipe.srem(_INDEX, approval_id)
        await pipe.execute()

        log.info("queue.resolved", approval_id=approval_id)
        return json.loads(data)

    async def get_expired(self) -> list[dict[str, Any]]:
        """
        Return all entries in the index that are no longer in Redis
        (i.e., their TTL has expired). Used by the timeout checker.
        Efficiently pipelined to prevent N+1 round trips.
        """
        all_ids = list(await self._redis.smembers(_INDEX))
        expired: list[dict[str, Any]] = []

        if not all_ids:
            return expired

        # 1. Pipeline check of all main keys
        pipe = self._redis.pipeline()
        for approval_id in all_ids:
            pipe.get(f"{_PREFIX}{approval_id}")
        main_keys_data = await pipe.execute()

        expired_ids = []
        for approval_id, data in zip(all_ids, main_keys_data, strict=False):
            if data is None:
                expired_ids.append(approval_id)
            else:
                # Belt-and-suspenders: check explicit expires_at timestamp
                entry = json.loads(data)
                expires_at = datetime.fromisoformat(entry["expires_at"])
                if datetime.now(UTC) >= expires_at:
                    expired_ids.append(approval_id)

        if expired_ids:
            # 2. Pipeline fetch of shadow metadata for expired items
            pipe_meta = self._redis.pipeline()
            for approval_id in expired_ids:
                pipe_meta.get(f"{_META_PREFIX}{approval_id}")
            meta_keys_data = await pipe_meta.execute()

            # 3. Clean up the expired items from Redis index and shadow keys
            pipe_cleanup = self._redis.pipeline()
            for approval_id in expired_ids:
                pipe_cleanup.delete(f"{_PREFIX}{approval_id}")
                pipe_cleanup.delete(f"{_META_PREFIX}{approval_id}")
                pipe_cleanup.srem(_INDEX, approval_id)
            await pipe_cleanup.execute()

            for data in meta_keys_data:
                if data:
                    expired.append(json.loads(data))

        return expired

    async def close(self) -> None:
        await self._redis.aclose()

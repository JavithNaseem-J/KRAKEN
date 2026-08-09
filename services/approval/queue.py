from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

_PREFIX = "kraken:approval:"
_INDEX = "kraken:approval:index"


class ApprovalQueue:
    """
    Manages pending HITL approval requests in Redis.
    One instance per service process, created in lifespan().
    """

    def __init__(self, redis_url: str, timeout_seconds: int = 900) -> None:
        from shared.http_client import create_async_redis_client

        self._redis: aioredis.Redis = create_async_redis_client(redis_url)
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

        pipe = self._redis.pipeline()
        pipe.set(key, json.dumps(entry), ex=self._timeout)
        pipe.sadd(_INDEX, approval_id)
        pipe.expire(_INDEX, self._timeout + 3600)
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

        # Atomically retrieve and delete key
        data = await self._redis.getdel(key)
        if data is None:
            return None

        # Clean up index
        await self._redis.srem(_INDEX, approval_id)

        log.info("queue.resolved", approval_id=approval_id)
        return json.loads(data)

    async def set_csrf_token(self, approval_id: str, token: str) -> None:
        """Store a CSRF token for an approval request."""
        try:
            await self._redis.set(f"kraken:csrf:{approval_id}", token, ex=self._timeout)
        except Exception as exc:
            log.warning("queue.csrf_set_failed", approval_id=approval_id, error=str(exc))

    async def verify_csrf_token(self, approval_id: str, token: str) -> bool:
        """Verify CSRF token for an approval request.

        Atomically reads-and-deletes the stored token (GETDEL) so it is
        single-use: a token that has already been verified cannot be replayed
        within its TTL window.  Fails closed on any error or absent token.
        """
        try:
            # GETDEL atomically retrieves and deletes the key — same pattern as resolve().
            expected = await self._redis.getdel(f"kraken:csrf:{approval_id}")
            if expected is None:
                # Token was never set, already consumed, or expired — reject.
                log.warning("queue.csrf_verify_no_token", approval_id=approval_id)
                return False
            return secrets.compare_digest(expected, token)
        except Exception as exc:
            log.warning("queue.csrf_verify_failed", approval_id=approval_id, error=str(exc))
            # Fail closed: Redis errors must not silently approve HITL decisions.
            return False

    async def close(self) -> None:
        await self._redis.aclose()

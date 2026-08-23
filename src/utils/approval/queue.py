from __future__ import annotations

import contextlib
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
    Manages pending HITL approval requests in Redis with in-memory fallback for degraded operation.
    One instance per service process, created in lifespan().
    """

    def __init__(self, redis_url: str, timeout_seconds: int = 900) -> None:
        from src.utils.http_client import create_async_redis_client

        self._redis: aioredis.Redis = create_async_redis_client(redis_url)
        self._timeout = timeout_seconds
        self._in_memory_map: dict[str, dict[str, Any]] = {}
        self._in_memory_csrf: dict[str, str] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Ping Redis to verify connection health."""
        try:
            await self._redis.ping()
            return True
        except Exception as exc:
            log.warning("queue.redis_ping_failed", error=str(exc))
            return False

    async def stats(self) -> int:
        """Return the count of pending approvals in the index."""
        try:
            return await self._redis.scard(_INDEX)
        except Exception:
            return len(self._in_memory_map)

    async def enqueue(
        self,
        action_name: str,
        payload: dict[str, Any],
        reasoning: str,
        session_id: str,
    ) -> str:
        """
        Register a new pending approval. Returns the approval_id.
        Entry expires automatically after timeout_seconds via Redis TTL or in-memory map.
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

        try:
            pipe = self._redis.pipeline()
            pipe.set(key, json.dumps(entry), ex=self._timeout)
            pipe.sadd(_INDEX, approval_id)
            pipe.expire(_INDEX, self._timeout + 3600)
            await pipe.execute()
        except Exception as exc:
            log.warning("queue.redis_enqueue_failed_using_in_memory", error=str(exc))
            self._in_memory_map[approval_id] = entry

        log.info("queue.enqueued", approval_id=approval_id, expires_at=expires_at)
        return approval_id

    async def get(self, approval_id: str) -> dict[str, Any] | None:
        """Return the pending entry, or None if expired/not found."""
        try:
            data = await self._redis.get(f"{_PREFIX}{approval_id}")
            if data:
                return json.loads(data)
        except Exception as exc:
            log.warning("queue.redis_get_failed_using_in_memory", error=str(exc))
        return self._in_memory_map.get(approval_id)

    async def resolve(self, approval_id: str) -> dict[str, Any] | None:
        """
        Remove an approval from the queue and return its data.
        Returns None if already resolved or expired.
        Uses atomic GETDEL to prevent race conditions.
        """
        key = f"{_PREFIX}{approval_id}"

        try:
            data = await self._redis.getdel(key)
            if data is not None:
                await self._redis.srem(_INDEX, approval_id)
                log.info("queue.resolved", approval_id=approval_id)
                return json.loads(data)
        except Exception as exc:
            log.warning("queue.redis_resolve_failed_using_in_memory", error=str(exc))

        entry = self._in_memory_map.pop(approval_id, None)
        if entry:
            log.info("queue.resolved_in_memory", approval_id=approval_id)
        return entry

    async def set_csrf_token(self, approval_id: str, token: str) -> None:
        """Store a CSRF token for an approval request."""
        try:
            await self._redis.set(f"kraken:csrf:{approval_id}", token, ex=self._timeout)
        except Exception as exc:
            log.warning(
                "queue.csrf_set_failed_using_in_memory", approval_id=approval_id, error=str(exc)
            )
            self._in_memory_csrf[approval_id] = token

    async def verify_csrf_token(self, approval_id: str, token: str) -> bool:
        """Verify CSRF token for an approval request."""
        try:
            expected = await self._redis.getdel(f"kraken:csrf:{approval_id}")
            if expected is not None:
                return secrets.compare_digest(str(expected), token)
        except Exception as exc:
            log.warning(
                "queue.csrf_verify_failed_using_in_memory", approval_id=approval_id, error=str(exc)
            )

        expected_local = self._in_memory_csrf.pop(approval_id, None)
        if expected_local is not None:
            return secrets.compare_digest(str(expected_local), token)
        return False

    def sweep_expired_in_memory(self) -> int:
        """Evict expired items from in-memory fallback dicts to prevent memory leaks."""
        now = datetime.now(UTC)
        expired_ids = [
            app_id
            for app_id, data in self._in_memory_map.items()
            if data.get("expires_at") and datetime.fromisoformat(data["expires_at"]) < now
        ]
        for app_id in expired_ids:
            self._in_memory_map.pop(app_id, None)
            self._in_memory_csrf.pop(app_id, None)
        return len(expired_ids)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._redis.aclose()

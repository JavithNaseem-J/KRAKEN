from __future__ import annotations

import contextlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog

from src.utils.privacy import strip_reasoning_fields

log = structlog.get_logger(__name__)


class ApprovalQueue:
    """
    Manages pending HITL approval requests in Redis with in-memory fallback for degraded operation.
    One instance per service process, created in lifespan().
    """

    def __init__(self, redis_url: str, timeout_seconds: int = 900) -> None:
        from src.utils.config import get_settings
        from src.utils.http_client import create_async_redis_client

        self._redis: aioredis.Redis = create_async_redis_client(redis_url)
        self._generation = get_settings().synthetic_dataset_generation
        self._prefix = f"kraken:{self._generation}:approval:"
        self._index = f"kraken:{self._generation}:approval:index"
        self._resolved_prefix = f"kraken:{self._generation}:approval:resolved:"
        self._csrf_prefix = f"kraken:{self._generation}:csrf:"
        self._timeout = timeout_seconds
        self._in_memory_map: dict[str, dict[str, Any]] = {}
        self._in_memory_csrf: dict[str, str] = {}
        self._in_memory_resolved: dict[str, datetime] = {}

    # Public API

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
            return await self._redis.scard(self._index)
        except Exception:
            return len(self._in_memory_map)

    async def enqueue(
        self,
        action_name: str,
        payload: dict[str, Any],
        session_id: str,
        initiator_id: str = "",
        initiator_role: str = "end_user",
        approval_id: str | None = None,
    ) -> str:
        """
        Register a new pending approval. Returns the approval_id.
        Entry expires automatically after timeout_seconds via Redis TTL or in-memory map.
        """
        approval_id = approval_id or str(uuid.uuid4())
        expires_at = (datetime.now(UTC) + timedelta(seconds=self._timeout)).isoformat()

        entry = {
            "approval_id": approval_id,
            "action_name": action_name,
            "payload": strip_reasoning_fields(payload),
            "session_id": session_id,
            "initiator_id": initiator_id,
            "initiator_role": initiator_role,
            "expires_at": expires_at,
            "status": "pending",
            "dataset_generation": self._generation,
        }

        key = f"{self._prefix}{approval_id}"
        resolved_key = f"{self._resolved_prefix}{approval_id}"

        try:
            if await self._redis.exists(resolved_key):
                return approval_id
            created = await self._redis.set(
                key,
                json.dumps(entry),
                ex=self._timeout,
                nx=True,
            )
            if created:
                pipe = self._redis.pipeline()
                pipe.sadd(self._index, approval_id)
                pipe.expire(self._index, self._timeout + 3600)
                await pipe.execute()
        except Exception as exc:
            log.warning("queue.redis_enqueue_failed_using_in_memory", error=str(exc))
            self.sweep_expired_in_memory()
            if approval_id in self._in_memory_resolved:
                return approval_id
            self._in_memory_map.setdefault(approval_id, entry)

        log.info("queue.enqueued", approval_id=approval_id, expires_at=expires_at)
        return approval_id

    async def purge_legacy_reasoning_entries(self) -> int:
        """Delete pending approvals written by schemas that persisted model reasoning."""
        removed = 0
        try:
            async for key in self._redis.scan_iter(match=f"{self._prefix}*"):
                key_text = key.decode() if isinstance(key, bytes) else str(key)
                if key_text == self._index or key_text.startswith(self._resolved_prefix):
                    continue
                raw = await self._redis.get(key)
                if not raw:
                    continue
                entry = json.loads(raw)
                if not isinstance(entry, dict) or "reasoning" not in entry:
                    continue
                approval_id = str(entry.get("approval_id", ""))
                pipe = self._redis.pipeline()
                pipe.delete(key)
                if approval_id:
                    pipe.srem(self._index, approval_id)
                await pipe.execute()
                removed += 1
        except Exception as exc:
            log.warning("queue.legacy_reasoning_purge_failed", error=str(exc))

        legacy_memory_ids = [
            approval_id
            for approval_id, entry in self._in_memory_map.items()
            if "reasoning" in entry
        ]
        for approval_id in legacy_memory_ids:
            self._in_memory_map.pop(approval_id, None)
            self._in_memory_csrf.pop(approval_id, None)
        removed += len(legacy_memory_ids)
        if removed:
            log.info("queue.legacy_reasoning_purged", count=removed)
        return removed

    async def get(self, approval_id: str) -> dict[str, Any] | None:
        """Return the pending entry, or None if expired/not found."""
        try:
            data = await self._redis.get(f"{self._prefix}{approval_id}")
            if data:
                entry = strip_reasoning_fields(json.loads(data))
                if entry.get("dataset_generation") == self._generation:
                    return entry
        except Exception as exc:
            log.warning("queue.redis_get_failed_using_in_memory", error=str(exc))
        self.sweep_expired_in_memory()
        return strip_reasoning_fields(self._in_memory_map.get(approval_id))

    async def resolve(self, approval_id: str) -> dict[str, Any] | None:
        """
        Remove an approval from the queue and return its data.
        Returns None if already resolved or expired.
        Uses atomic GETDEL to prevent race conditions.
        """
        key = f"{self._prefix}{approval_id}"

        try:
            data = await self._redis.getdel(key)
            if data is not None:
                pipe = self._redis.pipeline()
                pipe.srem(self._index, approval_id)
                pipe.set(f"{self._resolved_prefix}{approval_id}", "1", ex=self._timeout)
                await pipe.execute()
                log.info("queue.resolved", approval_id=approval_id)
                return strip_reasoning_fields(json.loads(data))
        except Exception as exc:
            log.warning("queue.redis_resolve_failed_using_in_memory", error=str(exc))

        self.sweep_expired_in_memory()
        entry = self._in_memory_map.pop(approval_id, None)
        if entry:
            self._in_memory_resolved[approval_id] = datetime.now(UTC) + timedelta(
                seconds=self._timeout
            )
            log.info("queue.resolved_in_memory", approval_id=approval_id)
        return strip_reasoning_fields(entry)

    async def set_csrf_token(self, approval_id: str, token: str) -> None:
        """Store a CSRF token for an approval request."""
        try:
            await self._redis.set(f"{self._csrf_prefix}{approval_id}", token, ex=self._timeout)
        except Exception as exc:
            log.warning(
                "queue.csrf_set_failed_using_in_memory", approval_id=approval_id, error=str(exc)
            )
            self._in_memory_csrf[approval_id] = token

    async def verify_csrf_token(self, approval_id: str, token: str) -> bool:
        """Verify CSRF token for an approval request."""
        try:
            expected = await self._redis.getdel(f"{self._csrf_prefix}{approval_id}")
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
        expired_resolved_ids = [
            app_id for app_id, expires_at in self._in_memory_resolved.items() if expires_at < now
        ]
        for app_id in expired_resolved_ids:
            self._in_memory_resolved.pop(app_id, None)
        return len(expired_ids) + len(expired_resolved_ids)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._redis.aclose()

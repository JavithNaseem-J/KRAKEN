from __future__ import annotations

import json
from typing import cast

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

_PREFIX = "kraken:session:"
_SESSION_TTL_SEC = 86_400  # 24 hours


class ShortTermMemory:
    """
    Redis-backed session message store.
    One instance per service process, created in lifespan().
    """

    def __init__(self, redis_url: str) -> None:
        from src.utils.http_client import create_async_redis_client

        self._redis: aioredis.Redis = create_async_redis_client(redis_url)

    def _key(self, session_id: str) -> str:
        return f"{_PREFIX}{session_id}"

    async def ping(self) -> bool:
        """Ping Redis to verify connectivity. Used during startup health check."""
        try:
            await self._redis.ping()
            return True
        except Exception as exc:
            log.error("short_term.redis_ping_failed", error=str(exc))
            return False

    async def get_session(self, session_id: str) -> list[dict[str, str]]:
        """Return all messages for the session, or [] if not found / expired."""
        data = await self._redis.get(self._key(session_id))
        if data is None:
            return []
        try:
            return cast(list[dict[str, str]], json.loads(data))
        except json.JSONDecodeError:
            log.error("short_term.corrupt_session", session_id=session_id)
            return []

    async def update_session(
        self,
        session_id: str,
        messages: list[dict[str, str]],
    ) -> None:
        """Replace the session message list and reset TTL."""
        await self._redis.set(
            self._key(session_id),
            json.dumps(messages),
            ex=_SESSION_TTL_SEC,
        )
        log.debug("short_term.updated", session_id=session_id, turns=len(messages))

    async def append_messages(
        self,
        session_id: str,
        new_messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """
        Atomically append new messages to the existing session history.

        Uses a Redis WATCH / MULTI / EXEC optimistic-lock transaction to
        prevent the lost-update race condition that occurs when two concurrent
        requests both read, modify, and write the same key.
        """
        key = self._key(session_id)

        async with self._redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    # WATCH — abort the transaction if the key changes before EXEC
                    await pipe.watch(key)

                    # Read current state inside the watched context
                    data = await self._redis.get(key)
                    existing = cast(list[dict[str, str]], json.loads(data)) if data else []
                    updated = existing + new_messages

                    # Begin atomic write block
                    pipe.multi()  # type: ignore[no-untyped-call]
                    pipe.set(key, json.dumps(updated), ex=_SESSION_TTL_SEC)
                    await pipe.execute()

                    log.debug(
                        "short_term.appended",
                        session_id=session_id,
                        added=len(new_messages),
                        total=len(updated),
                    )
                    return updated

                except aioredis.WatchError:
                    # Another writer modified the key — retry the whole loop
                    log.debug("short_term.append_retry", session_id=session_id)
                    continue

    async def clear_session(self, session_id: str) -> None:
        """Delete a session from Redis."""
        await self._redis.delete(self._key(session_id))
        log.info("short_term.cleared", session_id=session_id)

    async def close(self) -> None:
        await self._redis.aclose()

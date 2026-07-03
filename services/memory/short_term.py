"""
Short-term session memory using Redis.

Stores the conversation message history for each session.
Messages are a list of {role, content} dicts — the same format used
in the LangGraph AgentState `messages` field.

Key design:
  - Key:  akea:session:{session_id}  →  JSON list of messages
  - TTL:  SESSION_TTL_SECONDS (24 hours default) — renewed on every write
  - Append semantics: update_session() replaces entire list;
    append_messages() fetches + appends + stores atomically.
"""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)

_PREFIX          = "akea:session:"
_SESSION_TTL_SEC = 86_400   # 24 hours


class ShortTermMemory:
    """
    Redis-backed session message store.
    One instance per service process, created in lifespan().
    """

    def __init__(self, redis_url: str) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )

    def _key(self, session_id: str) -> str:
        return f"{_PREFIX}{session_id}"

    async def get_session(self, session_id: str) -> list[dict[str, str]]:
        """Return all messages for the session, or [] if not found / expired."""
        data = await self._redis.get(self._key(session_id))
        if data is None:
            return []
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            log.error("short_term.corrupt_session", session_id=session_id)
            return []

    async def update_session(
        self,
        session_id: str,
        messages: list[dict[str, str]],
    ) -> None:
        """Replace the session message list and reset TTL."""
        await self._redis.setex(
            self._key(session_id),
            _SESSION_TTL_SEC,
            json.dumps(messages),
        )
        log.debug("short_term.updated", session_id=session_id, turns=len(messages))

    async def append_messages(
        self,
        session_id: str,
        new_messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Append new messages to the existing session history."""
        existing = await self.get_session(session_id)
        updated  = existing + new_messages
        await self.update_session(session_id, updated)
        return updated

    async def clear_session(self, session_id: str) -> None:
        """Delete a session from Redis."""
        await self._redis.delete(self._key(session_id))
        log.info("short_term.cleared", session_id=session_id)

    async def close(self) -> None:
        await self._redis.aclose()

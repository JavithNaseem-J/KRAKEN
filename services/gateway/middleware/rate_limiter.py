"""
Sliding window rate limiter — Redis sorted-set implementation.

Algorithm:
  - Key:   akea:rl:{user_id}   (Redis sorted set)
  - Score: Unix timestamp of each request
  - Pipeline per request:
      1. ZADD   — record current request timestamp
      2. ZREMRANGEBYSCORE — evict entries older than the window
      3. ZCARD  — count requests still in the window
      4. EXPIRE — keep the key alive for one extra window cycle

Why sliding window over fixed window?
  Fixed window allows a burst of 2× the limit across a window boundary.
  Sliding window is accurate to the millisecond — no boundary burst possible.
  The sorted-set memory cost is O(max_requests) per user — negligible at 45-55 users.
"""
from __future__ import annotations

import time

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger(__name__)


class SlidingWindowRateLimiter:
    """
    Per-user sliding window rate limiter backed by Redis.
    One instance shared across all requests (created in lifespan).
    """

    def __init__(
        self,
        redis_url:      str,
        max_requests:   int = 10,
        window_seconds: int = 60,
    ) -> None:
        self._redis         = aioredis.from_url(redis_url, decode_responses=True)
        self._max           = max_requests
        self._window        = window_seconds

    async def check(self, user_id: str) -> tuple[bool, int, int]:
        """
        Check if a request from user_id is within rate limit.

        Returns:
            (is_allowed, remaining_requests, retry_after_seconds)
        """
        now          = time.time()
        window_start = now - self._window
        key          = f"akea:rl:{user_id}"

        pipe = self._redis.pipeline()
        pipe.zadd(key, {str(now): now})                 # Record this request
        pipe.zremrangebyscore(key, "-inf", window_start) # Evict stale entries
        pipe.zcard(key)                                  # Count in-window requests
        pipe.expire(key, self._window + 10)              # Keep key alive
        results = await pipe.execute()

        count     = int(results[2])
        allowed   = count <= self._max
        remaining = max(0, self._max - count)
        retry_after = int(self._window) if not allowed else 0

        if not allowed:
            log.warning(
                "rate_limiter.rejected",
                user_id=user_id,
                count=count,
                limit=self._max,
                retry_after=retry_after,
            )

        return allowed, remaining, retry_after

    async def close(self) -> None:
        await self._redis.aclose()

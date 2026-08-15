"""
Sliding window rate limiter — Redis sorted-set implementation using Lua script.

Algorithm:
  - Key:   kraken:rl:{user_id}   (Redis sorted set)
  - Score: Unix timestamp of each request
  - Uses an atomic Lua script to:
      1. Evict entries older than the window (ZREMRANGEBYSCORE)
      2. Count current entries (ZCARD)
      3. Check if count < limit
      4. If allowed: Add current request and set TTL
      5. If not allowed: Retrieve oldest entry score to calculate precise retry_after
  - Solves:
      1. Burst / Timing race conditions across concurrent nodes.
      2. Double counting of rejected requests (only allowed requests consume a slot).
      3. Accurate retry_after calculation.
      4. High concurrency member name collision.
"""

from __future__ import annotations

import time
import uuid

import structlog

log = structlog.get_logger(__name__)

# Atomic sliding window rate limiter Lua script
_LUA_LIMITER = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]

-- 1. Remove expired elements older than the sliding window start
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- 2. Count current elements in the window
local current_requests = redis.call('ZCARD', key)

if current_requests < max_requests then
    -- 3. Allowed: Record request and refresh TTL
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(now - window_start + 10))
    return {1, max_requests - current_requests - 1, 0}
else
    -- 4. Blocked: Find score of oldest element to calculate exact retry_after
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 0
    if oldest and oldest[2] then
        retry_after = math.ceil(tonumber(oldest[2]) - window_start)
    end
    if retry_after <= 0 then
        retry_after = 1
    end
    return {0, 0, retry_after}
end
"""


class RateLimiterDatabaseError(Exception):
    """Raised when the rate limiter backend (Redis) is unreachable or fails."""

    pass


class SlidingWindowRateLimiter:
    """
    Per-user sliding window rate limiter backed by Redis.
    Uses an atomic Lua script to guarantee correctness under load.
    """

    def __init__(
        self,
        redis_url: str,
        max_requests: int = 10,
        window_seconds: int = 60,
    ) -> None:
        from shared.http_client import create_async_redis_client

        self._redis = create_async_redis_client(redis_url)
        self._max = max_requests
        self._window = window_seconds
        # Register Lua script for execution efficiency and atomicity
        self._script = self._redis.register_script(_LUA_LIMITER)

    async def check(self, user_id: str) -> tuple[bool, int, int]:
        """
        Check if a request from user_id is within the rate limit.

        Returns:
            (is_allowed, remaining_requests, retry_after_seconds)

        Raises:
            RateLimiterDatabaseError: If connection to Redis fails.
        """
        now = time.time()
        window_start = now - self._window
        key = f"kraken:rl:{user_id}"
        # Unique member to prevent score/member collision when float time matches
        member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"

        try:
            results = await self._script(
                keys=[key], args=[str(now), str(window_start), str(self._max), member]
            )
            # Lua returns array: {allowed_int, remaining_int, retry_after_int}
            allowed = bool(results[0])
            remaining = int(results[1])
            retry_after = int(results[2])

            if not allowed:
                log.warning(
                    "rate_limiter.rejected",
                    user_id=user_id,
                    limit=self._max,
                    retry_after=retry_after,
                )

            return allowed, remaining, retry_after

        except Exception as exc:
            log.error(
                "rate_limiter.backend_failure", user_id=user_id, error=str(exc), exc_info=True
            )
            raise RateLimiterDatabaseError(
                f"Rate limiter database connection failed: {exc}"
            ) from exc

    async def close(self) -> None:
        await self._redis.aclose()

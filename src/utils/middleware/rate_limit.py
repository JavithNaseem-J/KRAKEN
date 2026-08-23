from __future__ import annotations

import time
import uuid
from collections import defaultdict
from collections.abc import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

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
        from src.utils.http_client import create_async_redis_client

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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory IP rate limiter middleware.
    Limits requests matching path_prefix to max_requests per window_seconds per client IP.
    """

    def __init__(
        self,
        app,
        path_prefix: str = "/approve/",
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.path_prefix = path_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path.startswith(self.path_prefix):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            cutoff = now - self.window_seconds

            # Clean expired timestamps for this IP
            timestamps = [t for t in self.requests.get(client_ip, []) if t > cutoff]
            if timestamps:
                self.requests[client_ip] = timestamps
            elif client_ip in self.requests:
                del self.requests[client_ip]

            # Periodic sweep if dictionary grows large
            if len(self.requests) > 500:
                expired_ips = [
                    ip for ip, ts in self.requests.items() if not ts or max(ts) <= cutoff
                ]
                for expired_ip in expired_ips:
                    self.requests.pop(expired_ip, None)

            if len(timestamps) >= self.max_requests:
                log.warning("rate_limit.exceeded", client_ip=client_ip, path=request.url.path)
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Please try again later."},
                    status_code=429,
                )

            self.requests[client_ip].append(now)

        return await call_next(request)

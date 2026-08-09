"""
In-memory IP rate limiter middleware for sensitive endpoints.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger(__name__)


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
            timestamps = [t for t in self.requests[client_ip] if t > cutoff]
            self.requests[client_ip] = timestamps

            if len(timestamps) >= self.max_requests:
                log.warning("rate_limit.exceeded", client_ip=client_ip, path=request.url.path)
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Please try again later."},
                    status_code=429,
                )

            self.requests[client_ip].append(now)

        return await call_next(request)

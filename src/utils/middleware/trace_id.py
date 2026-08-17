"""
Starlette/FastAPI Trace ID middleware for cross-service request correlation.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger(__name__)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """
    Extracts X-Trace-Id or X-Request-Id from request headers (or generates a UUID4),
    binds trace_id to structlog contextvars for the duration of the request,
    and returns X-Trace-Id in response headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = (
            request.headers.get("X-Trace-Id")
            or request.headers.get("X-Request-Id")
            or str(uuid.uuid4())
        )

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()

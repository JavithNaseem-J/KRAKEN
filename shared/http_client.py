"""
Shared HTTP client factory and inter-service authentication header helper.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from shared.config import get_settings

_DEFAULT_ASYNC_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)


def service_headers(
    token: str | None = None,
    trace_id: str | None = None,
) -> dict[str, str]:
    """Return standard inter-service authentication headers.

    Args:
        token: Explicit service token to use. When None, reads from settings.
        trace_id: Explicit trace ID to include in X-Trace-Id header. Fallback to structlog context.
    """
    resolved = token if token is not None else get_settings().hitl_service_token
    headers = {"X-Service-Token": resolved}

    if not trace_id:
        try:
            import structlog
            ctx = structlog.contextvars.get_contextvars()
            trace_id = ctx.get("trace_id")
        except Exception:
            trace_id = None

    if trace_id:
        headers["X-Trace-Id"] = trace_id
        headers["X-Request-Id"] = trace_id

    return headers


def create_async_http_client(
    timeout: httpx.Timeout | None = None,
    timeout_seconds: float | None = None,
) -> httpx.AsyncClient:
    """Create a configured asynchronous HTTP client for inter-service communication.

    Args:
        timeout:         Structured httpx.Timeout object. Takes precedence.
        timeout_seconds: Simple scalar fallback. Ignored when ``timeout`` is set.
    """
    if timeout is not None:
        resolved_timeout = timeout
    elif timeout_seconds is not None:
        resolved_timeout = httpx.Timeout(timeout_seconds)
    else:
        resolved_timeout = _DEFAULT_ASYNC_TIMEOUT
    return httpx.AsyncClient(timeout=resolved_timeout)


def create_async_redis_client(
    url: str,
    decode_responses: bool = True,
    socket_connect_timeout: float = 5.0,
    health_check_interval: int = 15,
) -> Any:
    """Create a configured asynchronous Redis client.

    Uses redis.asyncio with standard connection pooling, health checks, and keepalive options.
    """
    import redis.asyncio as aioredis

    redis_url = url if (url and url.strip()) else "redis://localhost:6379"

    return aioredis.from_url(
        redis_url,
        decode_responses=decode_responses,
        socket_connect_timeout=socket_connect_timeout,
        health_check_interval=health_check_interval,
        retry_on_timeout=True,
        socket_keepalive=True,
    )


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    reraise=True,
)
async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json_payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Execute an HTTP POST request with exponential backoff retries via tenacity.

    Retried on HTTP errors and timeouts up to 3 attempts.
    """
    resp = await client.post(url, json=json_payload, headers=headers)
    resp.raise_for_status()
    return resp


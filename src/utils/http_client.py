from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.utils.config import get_settings

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
    import sys

    import redis.asyncio as aioredis

    redis_url = url if (url and url.strip()) else "redis://localhost:6379"

    kwargs: dict[str, Any] = {
        "decode_responses": decode_responses,
        "socket_connect_timeout": socket_connect_timeout,
        "health_check_interval": health_check_interval,
        "retry_on_timeout": True,
    }
    if sys.platform != "win32":
        kwargs["socket_keepalive"] = True

    return aioredis.from_url(redis_url, **kwargs)


def get_in_process_app_for_url(url: str) -> Any | None:
    settings = get_settings()

    from src.api.action import app as act_app
    from src.api.approval import app as appr_app
    from src.api.audit import app as audit_app
    from src.api.knowledge import app as know_app
    from src.api.memory import app as mem_app
    from src.api.orchestrator import app as orch_app

    mapping = {
        settings.orchestrator_url: orch_app,
        settings.knowledge_url: know_app,
        settings.approval_url: appr_app,
        settings.memory_url: mem_app,
        settings.audit_url: audit_app,
        settings.action_url: act_app,
    }
    for base_url, target_app in mapping.items():
        if url.startswith(base_url):
            return target_app
    return None


def _is_retryable(exc: BaseException) -> bool:
    """Retry predicate: transport errors and 5xx responses only — never 4xx."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _is_mock_client(client: Any) -> bool:
    """Detect unittest-mocked clients so tests keep full control of the transport."""
    return type(client).__name__ in ("MagicMock", "AsyncMock", "Mock")


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    reraise=True,
)
async def internal_request(
    method: str,
    url: str,
    *,
    json_payload: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: Any | None = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> httpx.Response:
    """Issue an internal request to a subsystem URL (GET/POST/DELETE).

    URLs registered to an in-process sub-application are short-circuited via an
    ASGI transport, so no TCP listener is required. Retries (3 attempts,
    exponential backoff) fire only on transport errors and 5xx responses; 4xx
    responses raise immediately and are never retried.
    """
    resolved_method = method.upper()
    target_app = get_in_process_app_for_url(url)
    if target_app is not None and not _is_mock_client(client):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=target_app),
            base_url="http://internal",
            timeout=timeout_seconds,
        ) as in_proc_client:
            resp = await in_proc_client.request(
                resolved_method,
                url,
                json=json_payload,
                data=data,
                files=files,
                content=content,
                headers=headers,
            )
    elif client is not None:
        request_fn = getattr(client, resolved_method.lower())
        resp = await request_fn(
            url,
            json=json_payload,
            data=data,
            files=files,
            content=content,
            headers=headers,
        )
    else:
        async with create_async_http_client(timeout_seconds=timeout_seconds) as fallback_client:
            resp = await fallback_client.request(
                resolved_method,
                url,
                json=json_payload,
                data=data,
                files=files,
                content=content,
                headers=headers,
            )
    resp.raise_for_status()
    return resp


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json_payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Execute an HTTP POST with retries — thin wrapper over internal_request."""
    return await internal_request(
        "POST", url, json_payload=json_payload, headers=headers, client=client
    )


def get_app_http_client(app: Any) -> httpx.AsyncClient:
    """Return initialized HTTP client with lazy fallback."""
    client = getattr(app.state, "http", None)
    if client is None:
        client = create_async_http_client()
        app.state.http = client
    return client


def metrics_text(service_name: str) -> str:
    """Prometheus metrics endpoint text template parameterized by service name."""
    return (
        "# HELP kraken_service_up Liveness indicator (1 = healthy)\n"
        "# TYPE kraken_service_up gauge\n"
        f'kraken_service_up{{service="{service_name}"}} 1\n'
        "# HELP kraken_requests_total Total HTTP requests processed\n"
        "# TYPE kraken_requests_total counter\n"
        f'kraken_requests_total{{service="{service_name}"}} 1\n'
    )


def simple_health_response(service_name: str) -> dict[str, str]:
    """Standard health endpoint response for simple microservices."""
    return {"status": "ok", "service": service_name}

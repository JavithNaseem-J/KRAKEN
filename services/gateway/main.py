"""
API Gateway — single entry point for all external requests.

Responsibilities:
  1. API key authentication (X-API-Key header) via APIKeyMiddleware
  2. Sliding window rate limiting per user (backed by Redis Lua script)
  3. Request routing with header forwarding (X-Request-Id, X-Service-Token)
  4. Body size limit enforcement (max 1MB)
  5. Fail-safe configuration validation at startup

All internal services (orchestrator, knowledge, action, approval, memory, audit)
are NOT directly exposed. Only the gateway's port (8000) is published in docker-compose.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from shared.config import get_settings

from .middleware.auth import APIKeyMiddleware, parse_api_keys
from .middleware.rate_limiter import RateLimiterDatabaseError, SlidingWindowRateLimiter

log = structlog.get_logger(__name__)
settings = get_settings()

# Max allowed request body size: 1 MB (1024 * 1024 bytes)
MAX_BODY_SIZE = 1_048_576


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("gateway.startup")

    # 1. Fail fast at startup if API keys are empty or malformed
    try:
        app.state.api_keys = parse_api_keys(settings.gateway_api_keys)
    except Exception as exc:
        log.critical("gateway.startup_config_failed", error=str(exc))
        raise

    # 2. Initialize rate limiter
    limiter = SlidingWindowRateLimiter(
        redis_url=settings.redis_url,
        max_requests=settings.gateway_rate_limit_requests,
        window_seconds=settings.gateway_rate_limit_window_seconds,
    )
    app.state.limiter = limiter

    # 3. Shared HTTP client for upstream calls (connection pooling)
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0),
    )

    log.info("gateway.ready", orchestrator=settings.orchestrator_url)
    yield

    await app.state.limiter.close()
    await app.state.http.aclose()
    log.info("gateway.shutdown")


app = FastAPI(
    title="AKEA Gateway",
    description="API Gateway — Autonomous Knowledge Execution Agent",
    version="0.8.0",
    docs_url=None,  # Disable built-in docs for security
    lifespan=lifespan,
)

# ── Auth middleware (outermost layer for standard user API keys) ──────────────
app.add_middleware(
    APIKeyMiddleware,
    api_keys=parse_api_keys(settings.gateway_api_keys),
)


# ── Dependency: Enforce Service Token Auth for approvals ──────────────────────
def _verify_service_token(
    x_service_token: str | None = Header(None, alias="X-Service-Token"),
) -> str:
    """
    Enforce high-privilege service token authentication for approval callbacks.
    Uses timing-attack safe comparison.
    Always returns 403 (not 422) so the expected header name is not revealed.
    """
    # Treat missing token as empty string — compare_digest requires same types
    token = x_service_token or ""
    # Use a constant-time comparison against a fixed-length known value
    if not token or not secrets.compare_digest(token, settings.hitl_service_token):
        log.warning("gateway.approval_callback_auth_failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing service token.",
        )
    return token


# ── Dependency: Request Body Size Limiter ─────────────────────────────────────
async def _limit_request_body_size(request: Request) -> None:
    """
    Prevents large payloads (DoS) by checking Content-Length header
    and streaming a limited portion of the body.
    Caches the body in request._body so request.json() can read it downstream.
    """
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Request body too large. Max allowed is {MAX_BODY_SIZE} bytes.",
        )

    # Accumulate chunks up to MAX_BODY_SIZE to prevent DoS
    body_size = 0
    chunks = []
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > MAX_BODY_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Request body too large. Max allowed is {MAX_BODY_SIZE} bytes.",
            )
        chunks.append(chunk)

    # Cache the accumulated body in Starlette's internal attribute
    request._body = b"".join(chunks)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _rate_limit_headers(remaining: int, retry_after: int) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(settings.gateway_rate_limit_requests),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Window": f"{settings.gateway_rate_limit_window_seconds}s",
        **({"Retry-After": str(retry_after)} if retry_after > 0 else {}),
    }


async def _check_rate_limit(request: Request) -> tuple[bool, dict[str, str]]:
    user_id = getattr(request.state, "user_id", "anonymous")
    try:
        allowed, remaining, retry_after = await request.app.state.limiter.check(user_id)
        headers = _rate_limit_headers(remaining, retry_after)
        return allowed, headers
    except RateLimiterDatabaseError as exc:
        # Rate limiter is down — fail-closed/service unavailable is safer for security
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting database is temporarily unavailable.",
        ) from exc


async def _proxy(
    request: Request,
    upstream_url: str,
    body: dict,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Forward a request to an upstream service and return the response securely."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    user_id = getattr(request.state, "user_id", "anonymous")

    log.info(
        "gateway.proxy",
        user_id=user_id,
        upstream=upstream_url,
        request_id=request_id,
    )

    # Prepare forwarding headers
    forward_headers = {
        "X-Request-Id": request_id,
        "Content-Type": "application/json",
        "X-Service-Token": settings.hitl_service_token,
    }
    if headers:
        forward_headers.update(headers)

    # Inject user_id into JSON body for the upstream orchestrator state
    body["user_id"] = user_id

    try:
        resp = await request.app.state.http.post(
            upstream_url,
            json=body,
            headers=forward_headers,
        )

        # Handle upstream response parsing gracefully
        try:
            resp_data = resp.json()
        except ValueError:
            log.error("gateway.upstream_non_json", status_code=resp.status_code)
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"error": "Invalid JSON response from upstream service."},
                headers={"X-Request-Id": request_id},
            )

        return JSONResponse(
            content=resp_data,
            status_code=resp.status_code,
            headers={"X-Request-Id": request_id},
        )

    except httpx.TimeoutException:
        log.error("gateway.timeout", upstream=upstream_url)
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"error": "Upstream service timed out."},
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        log.error("gateway.proxy_error", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Upstream service unavailable."},
            headers={"X-Request-Id": request_id},
        )


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Gateway liveness check (does not leak internal network details)."""
    return {
        "status": "ok",
        "service": "gateway",
    }


@app.post(
    "/v1/run",
    tags=["agent"],
    dependencies=[Depends(_limit_request_body_size)],
)
async def run(request: Request) -> JSONResponse:
    """
    Submit a query to the agent.
    Rate limited per user. Proxied to orchestrator /run.
    """
    allowed, rl_headers = await _check_rate_limit(request)
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Rate limit exceeded. Try again shortly."},
            headers=rl_headers,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Invalid JSON body."}
        )

    # Ensure session_id is generated if not provided
    body.setdefault("session_id", str(uuid.uuid4()))

    response = await _proxy(request, f"{settings.orchestrator_url}/run", body)

    # Attach rate limit headers to response
    for k, v in rl_headers.items():
        response.headers[k] = v
    return response


@app.post(
    "/v1/approval-callback",
    tags=["hitl"],
    dependencies=[Depends(_limit_request_body_size)],
)
async def approval_callback(
    request: Request,
    service_token: str = Depends(_verify_service_token),
) -> JSONResponse:
    """
    Forward an approval decision to the orchestrator.
    Requires X-Service-Token header validation.
    Forward the service token header so orchestrator can authenticate.
    """
    allowed, rl_headers = await _check_rate_limit(request)
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Rate limit exceeded. Try again shortly."},
            headers=rl_headers,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Invalid JSON body."}
        )

    # Forward the X-Service-Token downstream so orchestrator is satisfied
    headers = {"X-Service-Token": service_token}

    response = await _proxy(
        request,
        f"{settings.orchestrator_url}/approval-callback",
        body,
        headers=headers,
    )

    # Attach rate limit headers to response
    for k, v in rl_headers.items():
        response.headers[k] = v
    return response

"""
API Gateway — single entry point for all external requests.

Responsibilities:
  1. API key authentication (X-API-Key header)
  2. Sliding window rate limiting (10 req/min per user by default)
  3. Request routing → orchestrator service
  4. Response enrichment (X-Request-Id, X-RateLimit-* headers)

All internal services (orchestrator, knowledge, action, approval, memory, audit)
are NOT directly exposed. Only the gateway's port (8000) is published in docker-compose.

Endpoints proxied to orchestrator:
  POST /v1/run                  →  POST orchestrator/run
  POST /v1/approval-callback    →  POST orchestrator/approval-callback

Direct gateway endpoints:
  GET  /health                  Gateway liveness (also probes orchestrator)
  GET  /v1/docs                 Redirects to orchestrator OpenAPI
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.config import get_settings
from .middleware.rate_limiter import SlidingWindowRateLimiter
from .middleware.auth import APIKeyMiddleware, parse_api_keys

log      = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("gateway.startup")

    # ── Rate limiter ──────────────────────────────────────────────────────────
    limiter = SlidingWindowRateLimiter(
        redis_url=settings.redis_url,
        max_requests=settings.gateway_rate_limit_requests,
        window_seconds=settings.gateway_rate_limit_window_seconds,
    )
    app.state.limiter = limiter

    # ── Shared HTTP client for upstream calls ─────────────────────────────────
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0),
    )

    log.info("gateway.ready", orchestrator=settings.orchestrator_url)
    yield

    await app.state.limiter.close()
    await app.state.http.aclose()
    log.info("gateway.shutdown")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AKEA Gateway",
    description="API Gateway — Autonomous Knowledge Execution Agent",
    version="0.7.0",
    docs_url=None,    # Disable built-in docs (gateway proxies to orchestrator docs)
    lifespan=lifespan,
)

# ── Auth middleware (outermost layer) ─────────────────────────────────────────
app.add_middleware(
    APIKeyMiddleware,
    api_keys=parse_api_keys(settings.gateway_api_keys),
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _rate_limit_headers(remaining: int, retry_after: int) -> dict[str, str]:
    return {
        "X-RateLimit-Limit":     str(settings.gateway_rate_limit_requests),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Window":    f"{settings.gateway_rate_limit_window_seconds}s",
        **({"Retry-After": str(retry_after)} if retry_after > 0 else {}),
    }


async def _check_rate_limit(request: Request) -> tuple[bool, dict[str, str]]:
    user_id = getattr(request.state, "user_id", "anonymous")
    allowed, remaining, retry_after = await request.app.state.limiter.check(user_id)
    headers = _rate_limit_headers(remaining, retry_after)
    return allowed, headers


async def _proxy(
    request: Request,
    upstream_url: str,
    body: dict,
) -> JSONResponse:
    """Forward a request to an upstream service and return the response."""
    request_id = str(uuid.uuid4())
    user_id    = getattr(request.state, "user_id", "anonymous")

    log.info(
        "gateway.proxy",
        user_id=user_id,
        upstream=upstream_url,
        request_id=request_id,
    )

    # Inject user_id into body so orchestrator can use it
    body["user_id"] = user_id

    try:
        resp = await request.app.state.http.post(upstream_url, json=body)
        return JSONResponse(
            content=resp.json(),
            status_code=resp.status_code,
            headers={"X-Request-Id": request_id},
        )
    except httpx.TimeoutException:
        log.error("gateway.timeout", upstream=upstream_url)
        return JSONResponse(
            status_code=504,
            content={"error": "Upstream service timed out."},
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        log.error("gateway.proxy_error", error=str(exc))
        return JSONResponse(
            status_code=502,
            content={"error": "Upstream service unavailable."},
            headers={"X-Request-Id": request_id},
        )


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    """Gateway liveness + orchestrator reachability check."""
    orchestrator_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.orchestrator_url}/health")
            orchestrator_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status":      "ok",
        "service":     "gateway",
        "orchestrator": orchestrator_ok,
    }


@app.post("/v1/run", tags=["agent"])
async def run(request: Request) -> JSONResponse:
    """
    Submit a query to the agent.
    Rate limited per user. Proxied to orchestrator /run.
    """
    allowed, rl_headers = await _check_rate_limit(request)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Try again shortly."},
            headers=rl_headers,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body."})

    # Ensure session_id is set
    body.setdefault("session_id", str(uuid.uuid4()))

    response = await _proxy(request, f"{settings.orchestrator_url}/run", body)

    # Attach rate limit headers to response
    for k, v in rl_headers.items():
        response.headers[k] = v
    return response


@app.post("/v1/approval-callback", tags=["hitl"])
async def approval_callback(request: Request) -> JSONResponse:
    """
    Forward an approval decision to the orchestrator.
    Rate limited to prevent callback flooding.
    """
    allowed, rl_headers = await _check_rate_limit(request)
    if not allowed:
        return JSONResponse(status_code=429, content={"error": "Rate limit exceeded."})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body."})

    return await _proxy(
        request,
        f"{settings.orchestrator_url}/approval-callback",
        body,
    )

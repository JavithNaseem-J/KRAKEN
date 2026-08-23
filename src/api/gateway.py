from __future__ import annotations

import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
import structlog
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import ValidationError

from src.utils.auth import APIKeyMiddleware, parse_api_keys
from src.utils.config import get_settings
from src.utils.cors import cors_middleware_kwargs
from src.utils.http_client import (
    create_async_http_client,
    get_in_process_app_for_url,
    internal_request,
    metrics_text,
    service_headers,
    simple_health_response,
)
from src.utils.logging import configure_logging
from src.utils.middleware.prompt_guard import (
    PromptGuardMiddleware,
    check_prompt_injection,
    sanitize_pii,
)
from src.utils.middleware.rate_limit import RateLimiterDatabaseError, SlidingWindowRateLimiter
from src.utils.middleware.trace_id import TraceIdMiddleware

log = structlog.get_logger(__name__)
settings = get_settings()

# Max allowed request body size: 1 MB (1024 * 1024 bytes)
MAX_BODY_SIZE = 1_048_576
API_KEYS_MAP = parse_api_keys(settings.gateway_api_keys)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="gateway"
    )
    log.info("gateway.startup")

    app.state.api_keys = API_KEYS_MAP

    # 2. Initialize rate limiter
    limiter = SlidingWindowRateLimiter(
        redis_url=settings.redis_url,
        max_requests=settings.gateway_rate_limit_requests,
        window_seconds=settings.gateway_rate_limit_window_seconds,
    )
    app.state.limiter = limiter

    # 3. Shared HTTP client for upstream calls (connection pooling)
    app.state.http = create_async_http_client()

    # 4. Boot every sub-application in dependency order by entering its
    #    lifespan context. A failing subsystem logs `<name>.degraded` and the
    #    gateway keeps booting; contexts are exited in reverse on shutdown.
    from src.api.action import app as action_app
    from src.api.approval import app as approval_app
    from src.api.audit import app as audit_app
    from src.api.knowledge import app as knowledge_app
    from src.api.memory import app as memory_app
    from src.api.orchestrator import app as orchestrator_app

    sub_apps: tuple[tuple[str, FastAPI], ...] = (
        ("knowledge", knowledge_app),
        ("memory", memory_app),
        ("audit", audit_app),
        ("action", action_app),
        ("approval", approval_app),
        ("orchestrator", orchestrator_app),
    )

    entered: list[tuple[str, Any]] = []
    degraded: list[str] = []
    for name, sub_app in sub_apps:
        try:
            context = sub_app.router.lifespan_context(sub_app)
            await context.__aenter__()
            entered.append((name, context))
            log.info("gateway.subapp_ready", subsystem=name)
        except Exception as exc:
            degraded.append(name)
            log.error(f"{name}.degraded", error=str(exc))

    app.state.subapp_contexts = entered
    app.state.subapps_degraded = degraded

    log.info(
        "gateway.ready",
        orchestrator=settings.orchestrator_url,
        degraded=degraded,
    )
    yield

    for name, context in reversed(entered):
        try:
            await context.__aexit__(None, None, None)
        except Exception as exc:
            log.warning("gateway.subapp_shutdown_failed", subsystem=name, error=str(exc))

    await app.state.limiter.close()
    await app.state.http.aclose()
    log.info("gateway.shutdown")


app = FastAPI(
    title="KRAKEN Gateway",
    description="API Gateway — KRAKEN",
    version="0.6.0",
    docs_url=None,  # Disable built-in docs for security
    lifespan=lifespan,
)

# ── Auth & Security middleware ────────────────────────────────────────────────
app.add_middleware(TraceIdMiddleware)
app.add_middleware(PromptGuardMiddleware)
app.add_middleware(
    APIKeyMiddleware,
    api_keys=API_KEYS_MAP,
)

# ── CORS (React frontend origins) ─────────────────────────────────────────────
# Starlette runs middleware in reverse add order, so CORS is added LAST to run
# FIRST — preflight OPTIONS requests must be answered before auth rejects them.
app.add_middleware(
    CORSMiddleware,
    **cors_middleware_kwargs(),
)


@app.get("/metrics", tags=["ops"])
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint for gateway service."""
    return PlainTextResponse(content=metrics_text("gateway"))


# ── Dependency: Request Body Size Limiter ─────────────────────────────────────
async def _limit_request_body_size(request: Request) -> None:
    """
    Prevents large payloads (DoS) by checking Content-Length header
    and validating body size.
    """
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Request body too large. Max allowed is {MAX_BODY_SIZE} bytes.",
        )

    body = await request.body()
    if len(body) > MAX_BODY_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Request body too large. Max allowed is {MAX_BODY_SIZE} bytes.",
        )


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
        log.warning("gateway.rate_limit_degraded_fail_open", user_id=user_id, error=str(exc))
        headers = _rate_limit_headers(settings.gateway_rate_limit_requests, 0)
        return True, headers


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
    forward_headers = service_headers(trace_id=request_id)
    forward_headers.update(
        {
            "X-Request-Id": request_id,
            "Content-Type": "application/json",
        }
    )
    if headers:
        forward_headers.update(headers)

    # Inject user_id into JSON body for the upstream orchestrator state
    body["user_id"] = user_id

    try:
        is_mock_http = type(getattr(request.app.state, "http", None)).__name__ in ("MagicMock", "AsyncMock", "Mock")
        target_app = None if is_mock_http else get_in_process_app_for_url(upstream_url)
        if target_app is not None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=target_app), base_url="http://internal", timeout=120.0
            ) as client:
                resp = await client.post(upstream_url, json=body, headers=forward_headers)
        else:
            resp = await request.app.state.http.post(
                upstream_url,
                json=body,
                headers=forward_headers,
            )

        # Handle upstream response parsing gracefully
        try:
            resp_data = resp.json()
        except ValueError:
            raw = resp.text[:300] if resp.text else "Empty response"
            log.error("gateway.upstream_non_json", status_code=resp.status_code, body=raw)
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"error": f"Upstream service error ({resp.status_code}): {raw}"},
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
    return simple_health_response("gateway")


@app.get("/ready", tags=["ops"])
async def ready_check(request: Request) -> JSONResponse:
    """
    Aggregated readiness probe — checks health of all downstream subsystems.
    Subsystem health checks are short-circuited in-process (no TCP listeners).
    """
    services = {
        "orchestrator": settings.orchestrator_url,
        "knowledge": settings.knowledge_url,
        "action": settings.action_url,
        "approval": settings.approval_url,
        "memory": settings.memory_url,
        "audit": settings.audit_url,
    }

    degraded_at_boot = set(getattr(request.app.state, "subapps_degraded", []))

    results: dict[str, str] = {}
    all_ready = True

    for name, base_url in services.items():
        if name in degraded_at_boot:
            results[name] = "degraded (startup failed)"
            all_ready = False
            continue
        try:
            # A 200 from the subsystem's own /health proves its lifespan ran
            # and it is serving (backing services fail open by design).
            resp = await internal_request("GET", f"{base_url}/health", timeout_seconds=5.0)
            if resp.status_code == 200:
                results[name] = "ok"
            else:
                results[name] = f"degraded ({resp.status_code})"
                all_ready = False
        except Exception as exc:
            results[name] = f"unreachable ({exc.__class__.__name__})"
            all_ready = False

    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_ready else "degraded", "services": results},
    )


@app.get("/", tags=["ops"])
async def root() -> dict[str, Any]:
    return {
        "service": "gateway",
        "description": "KRAKEN Edge API Gateway",
        "documentation": "/docs",
        "health": "/health",
        "frontend": "http://localhost:5173",
    }


# ── Operator-Privilege Intent Gate ───────────────────────────────────────────
# Keywords that signal a state-mutating / high-privilege operation intent.
# If a message contains these keywords the request MUST carry
# the X-Operator-Role: operator header, otherwise it is denied before the LLM
# is ever invoked — preventing ticket data leakage via the HITL approval card.
_HIGH_PRIVILEGE_PATTERNS = re.compile(
    r"\b(escalate|write\s+(?:a\s+)?(?:json|report|file)|close\s+ticket|"
    r"delete|purge|remove\s+ticket|wipe|create\s+(?:a\s+)?(?:new\s+)?ticket)\b",
    re.IGNORECASE,
)

_ALLOWED_OPERATOR_ROLES: frozenset[str] = frozenset(
    {"operator", "tier1_analyst", "incident_commander", "security_lead", "admin", "soc_tier1", "soc_tier2"}
)


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

    # Ensure session_id and user_id defaults if not provided
    if isinstance(body, dict):
        body.setdefault("session_id", str(uuid.uuid4()))
        body.setdefault("user_id", "anonymous")

    message = body.get("message", "") if isinstance(body, dict) else ""
    if isinstance(message, str) and message:
        is_operator = request.headers.get("X-Operator-Role", "").strip().lower() in _ALLOWED_OPERATOR_ROLES
        if check_prompt_injection(message) and not is_operator:
            log.warning("gateway.prompt_injection_blocked", path=request.url.path)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Request blocked: potential prompt injection detected."},
            )
        sanitized = sanitize_pii(message)
        if sanitized != message:
            body["message"] = sanitized
            message = sanitized

    # ── Operator Privilege Intent Gate ────────────────────────────────────────
    # Check if the message contains high-privilege operational intent keywords.
    # If so, require the X-Operator-Role: operator header before forwarding.
    # This prevents unauthenticated users from triggering HITL cards that
    # expose internal ticket data.
    if isinstance(message, str) and _HIGH_PRIVILEGE_PATTERNS.search(message):
        operator_role = request.headers.get("X-Operator-Role", "").strip().lower()
        if operator_role not in _ALLOWED_OPERATOR_ROLES:
            user_id = getattr(request.state, "user_id", "anonymous")
            log.warning(
                "gateway.privilege_escalation_denied",
                user_id=user_id,
                message_preview=message[:80],
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": (
                        "Access denied. This operation requires operator-level clearance. "
                        "Please contact your security administrator to request elevated access."
                    )
                },
            )

    try:
        from src.utils.models.agent import QueryRequest

        QueryRequest.model_validate(body)
    except ValidationError as err:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "Invalid request payload", "details": err.errors(include_url=False)},
        )

    response = await _proxy(request, f"{settings.orchestrator_url}/run", body)

    # Attach rate limit headers to response
    for k, v in rl_headers.items():
        response.headers[k] = v
    return response


@app.post(
    "/v1/run/stream",
    tags=["agent"],
    response_model=None,
    dependencies=[Depends(_limit_request_body_size)],
)
async def run_stream(request: Request) -> Any:
    """
    Submit a query to the agent with real-time SSE streaming.
    Rate limited per user. Proxied to orchestrator /run/stream.
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

    user_id = getattr(request.state, "user_id", "anonymous")
    if isinstance(body, dict):
        body.setdefault("session_id", str(uuid.uuid4()))
        body["user_id"] = user_id

    message = body.get("message", "") if isinstance(body, dict) else ""
    if isinstance(message, str) and message:
        is_operator = request.headers.get("X-Operator-Role", "").strip().lower() in _ALLOWED_OPERATOR_ROLES
        if check_prompt_injection(message) and not is_operator:
            log.warning("gateway.prompt_injection_blocked", path=request.url.path)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Request blocked: potential prompt injection detected."},
            )
        sanitized = sanitize_pii(message)
        if sanitized != message:
            body["message"] = sanitized
            message = sanitized

    if isinstance(message, str) and _HIGH_PRIVILEGE_PATTERNS.search(message):
        operator_role = request.headers.get("X-Operator-Role", "").strip().lower()
        if operator_role not in _ALLOWED_OPERATOR_ROLES:
            log.warning(
                "gateway.privilege_escalation_denied",
                user_id=user_id,
                message_preview=message[:80],
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": (
                        "Access denied. This operation requires operator-level clearance. "
                        "Please contact your security administrator to request elevated access."
                    )
                },
            )

    try:
        from src.utils.models.agent import QueryRequest

        QueryRequest.model_validate(body)
    except ValidationError as err:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "Invalid request payload", "details": err.errors(include_url=False)},
        )

    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    forward_headers = service_headers(trace_id=request_id)
    forward_headers.update({
        "X-Request-Id": request_id,
        "Content-Type": "application/json",
    })

    async def stream_generator():
        is_mock_http = type(getattr(request.app.state, "http", None)).__name__ in ("MagicMock", "AsyncMock", "Mock")
        target_app = None if is_mock_http else get_in_process_app_for_url(settings.orchestrator_url)
        if target_app is not None:
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=target_app), base_url="http://internal", timeout=120.0
                ) as client,
                client.stream(
                    "POST",
                    f"{settings.orchestrator_url}/run/stream",
                    json=body,
                    headers=forward_headers,
                    timeout=120.0,
                ) as upstream_resp,
            ):
                async for chunk in upstream_resp.aiter_bytes():
                    yield chunk
        else:
            client: httpx.AsyncClient = request.app.state.http
            async with client.stream(
                "POST",
                f"{settings.orchestrator_url}/run/stream",
                json=body,
                headers=forward_headers,
                timeout=120.0,
            ) as upstream_resp:
                async for chunk in upstream_resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            **rl_headers,
        },
    )


# ── HITL approval proxy routes (single-port browser flow) ─────────────────────
@app.get("/approve/{approval_id}/details", tags=["hitl"])
async def approval_details_proxy(request: Request, approval_id: str) -> JSONResponse:
    """Proxy approval details + CSRF token to the in-process approval app."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    url = f"{settings.approval_url}/approve/{approval_id}/details"
    try:
        resp = await internal_request("GET", url, headers={"X-Request-Id": request_id})
        return JSONResponse(
            content=resp.json(),
            status_code=resp.status_code,
            headers={"X-Request-Id": request_id},
        )
    except httpx.HTTPStatusError as exc:
        try:
            content = exc.response.json()
        except ValueError:
            content = {"error": exc.response.text[:300]}
        return JSONResponse(
            content=content,
            status_code=exc.response.status_code,
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        log.error("gateway.approval_details_proxy_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Approval service unavailable."},
            headers={"X-Request-Id": request_id},
        )


@app.post("/approve/{approval_id}/decision", tags=["hitl"])
async def approval_decision_proxy(request: Request, approval_id: str) -> Response:
    """Proxy the approve/reject form submission to the in-process approval app."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    body = await request.body()
    if len(body) > MAX_BODY_SIZE:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"error": f"Request body too large. Max allowed is {MAX_BODY_SIZE} bytes."},
            headers={"X-Request-Id": request_id},
        )
    content_type = request.headers.get("content-type", "application/x-www-form-urlencoded")
    url = f"{settings.approval_url}/approve/{approval_id}/decision"
    try:
        resp = await internal_request(
            "POST",
            url,
            content=body,
            headers={"Content-Type": content_type, "X-Request-Id": request_id},
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type"),
            headers={"X-Request-Id": request_id},
        )
    except httpx.HTTPStatusError as exc:
        return Response(
            content=exc.response.content,
            status_code=exc.response.status_code,
            media_type=exc.response.headers.get("content-type"),
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        log.error("gateway.approval_decision_proxy_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Approval service unavailable."},
            headers={"X-Request-Id": request_id},
        )


@app.post("/v1/knowledge/upload", tags=["knowledge"])
async def upload_knowledge(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    allowed_roles: Annotated[str, Form()] = "public",
) -> JSONResponse:
    """Proxy multipart file upload to Knowledge Service."""
    request_id = str(uuid.uuid4())
    headers = service_headers(trace_id=request_id)
    try:
        content_bytes = await file.read()
        files = {"file": (file.filename, content_bytes, file.content_type)}
        data = {"allowed_roles": allowed_roles}
        async with create_async_http_client(timeout_seconds=60.0) as client:
            resp = await client.post(
                f"{settings.knowledge_url}/upload",
                files=files,
                data=data,
                headers=headers,
            )
            return JSONResponse(
                content=resp.json(),
                status_code=resp.status_code,
                headers={"X-Request-Id": request_id},
            )
    except Exception as exc:
        log.error("gateway.upload_proxy_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": f"Upload failed: {exc}"},
            headers={"X-Request-Id": request_id},
        )


@app.post("/v1/report/export", tags=["report"])
async def export_report(request: Request) -> Response:
    """
    Generate and export a formatted Executive Incident Briefing PDF report for a session.
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Invalid JSON body."}
        )

    messages = payload.get("messages", [])
    if not messages:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Session has no messages to export"},
        )

    from .report import generate_incident_html

    html = generate_incident_html(payload)
    session_id = payload.get("session_id", "incident")[:8]
    filename = f"kraken-incident-{session_id}.html"

    return Response(
        content=html.encode("utf-8"),
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Accel-Buffering": "no",
        },
    )


# ── Audit proxy routes ────────────────────────────────────────────────────────
@app.get("/v1/audit/events/{trace_id}", tags=["audit"])
@app.get("/v1/audit/history/{trace_id}", tags=["audit"])
async def audit_history_proxy(request: Request, trace_id: str) -> JSONResponse:
    """Proxy audit events by session or trace ID to the Audit service."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    url = f"{settings.audit_url}/history/{trace_id}"
    try:
        resp = await internal_request("GET", url, headers={"X-Request-Id": request_id})
        return JSONResponse(
            content=resp.json(),
            status_code=resp.status_code,
            headers={"X-Request-Id": request_id},
        )
    except httpx.HTTPStatusError as exc:
        try:
            content = exc.response.json()
        except ValueError:
            content = {"error": exc.response.text[:300]}
        return JSONResponse(
            content=content,
            status_code=exc.response.status_code,
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        log.error("gateway.audit_history_proxy_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Audit service unavailable."},
            headers={"X-Request-Id": request_id},
        )



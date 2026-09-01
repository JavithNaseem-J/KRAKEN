from __future__ import annotations

import asyncio
import ipaddress
import re
import secrets
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
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
    guard_message,
    is_operator_role,
)
from src.utils.middleware.rate_limit import RateLimiterDatabaseError, SlidingWindowRateLimiter
from src.utils.middleware.trace_id import TraceIdMiddleware
from src.utils.models.agent import QueryRequest
from src.utils.models.public import (
    CapabilityState,
    CapabilityStatus,
    CsrfProof,
    PersonaTransitionRequest,
    PersonaTransitionResponse,
    PublicSessionResetResponse,
    ReadinessResponse,
)
from src.utils.public_sessions import (
    PublicSession,
    PublicSessionError,
    PublicSessionExpiredError,
    PublicSessionManager,
)
from src.utils.registry import get_privileged_action_terms

log = structlog.get_logger(__name__)
settings = get_settings()

# Max allowed request body size: 1 MB (1024 * 1024 bytes)
MAX_BODY_SIZE = 1_048_576
API_KEYS_MAP = parse_api_keys(settings.gateway_api_keys)
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend-react" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="gateway"
    )
    log.info("gateway.startup")

    app.state.api_keys = API_KEYS_MAP
    app.state.public_sessions = PublicSessionManager(settings)

    # 2. Initialize rate limiter
    limiter = SlidingWindowRateLimiter(
        redis_url=settings.redis_url,
        max_requests=settings.public_query_limit,
        window_seconds=settings.public_query_window_seconds,
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
    await app.state.public_sessions.close()
    await app.state.http.aclose()
    log.info("gateway.shutdown")


app = FastAPI(
    title="KRAKEN Gateway",
    description="API Gateway — KRAKEN",
    version="0.6.0",
    docs_url=None,  # Disable built-in docs for security
    lifespan=lifespan,
)

# Auth & Security middleware
app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    APIKeyMiddleware,
    api_keys=API_KEYS_MAP,
)

# CORS (React frontend origins)
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


# Dependency: Request Body Size Limiter
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


# Helpers
def _rate_limit_headers(remaining: int, retry_after: int) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(settings.public_query_limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Window": f"{settings.public_query_window_seconds}s",
        **({"Retry-After": str(retry_after)} if retry_after > 0 else {}),
    }


def _rate_limit_client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    if not _is_trusted_forwarding_hop(direct_ip):
        return direct_ip

    for header in ("x-forwarded-for", "x-real-ip"):
        value = request.headers.get(header)
        if not value:
            continue
        candidate = value.split(",", 1)[0].strip().strip('"').strip("[]")
        if _is_ip_address(candidate):
            return candidate
    return direct_ip


def _is_trusted_forwarding_hop(host: str) -> bool:
    if host in {"testclient", "localhost", "unknown"}:
        return True
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return False
    return parsed.is_loopback or parsed.is_private or parsed.is_link_local


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


async def _check_rate_limit(request: Request) -> tuple[bool, dict[str, str]]:
    client_ip = _rate_limit_client_ip(request)
    try:
        allowed, remaining, retry_after = await request.app.state.limiter.check(client_ip)
        headers = _rate_limit_headers(remaining, retry_after)
        return allowed, headers
    except RateLimiterDatabaseError as exc:
        manager = _public_session_manager(request)
        allowed, remaining, retry_after = manager.check_query_limit(client_ip)
        log.warning(
            "gateway.rate_limit_fallback", client_ip=client_ip, error=exc.__class__.__name__
        )
        return allowed, _rate_limit_headers(remaining, retry_after)


def _public_session_manager(request: Request) -> PublicSessionManager:
    manager = getattr(request.app.state, "public_sessions", None)
    if manager is None:
        manager = PublicSessionManager(settings)
        request.app.state.public_sessions = manager
    return manager


async def _resolve_public_session(
    request: Request, *, required: bool = False
) -> PublicSession | None:
    cookie = request.cookies.get(settings.public_session_cookie_name)
    if not cookie and not required:
        return None
    try:
        manager = _public_session_manager(request)
        try:
            return manager.resolve(cookie)
        except PublicSessionError:
            return await manager.restore(cookie)
    except PublicSessionExpiredError as exc:
        raise HTTPException(status_code=401, detail="Public session expired.") from exc
    except PublicSessionError as exc:
        raise HTTPException(status_code=401, detail="Invalid public session.") from exc


def _set_public_cookie(response: Response, cookie_value: str) -> None:
    response.set_cookie(
        key=settings.public_session_cookie_name,
        value=cookie_value,
        max_age=settings.public_session_ttl_seconds,
        httponly=True,
        secure=settings.public_cookie_secure,
        samesite="lax",
        path="/",
    )


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

    # Preserve the server-validated public actor prepared for agent requests.
    body.setdefault("user_id", user_id)

    try:
        is_mock_http = type(getattr(request.app.state, "http", None)).__name__ in (
            "MagicMock",
            "AsyncMock",
            "Mock",
        )
        target_app = None if is_mock_http else get_in_process_app_for_url(upstream_url)
        if target_app is not None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=target_app),
                base_url="http://internal",
                timeout=120.0,
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
            log.error("gateway.upstream_non_json", status_code=resp.status_code)
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"error": "Upstream service returned an invalid response."},
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
        log.error("gateway.proxy_error", error=exc.__class__.__name__)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Upstream service unavailable."},
            headers={"X-Request-Id": request_id},
        )


# Routes
@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Gateway liveness check (does not leak internal network details)."""
    return simple_health_response("gateway")


@app.post("/v1/session", status_code=status.HTTP_201_CREATED, tags=["session"])
async def create_public_session(request: Request) -> JSONResponse:
    """Issue a clean anonymous public identity without exposing server credentials."""
    manager = _public_session_manager(request)
    session, cookie = manager.create()
    await manager.persist(session)
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=manager.response(session).model_dump(mode="json"),
    )
    _set_public_cookie(response, cookie)
    return response


@app.get("/v1/sessions/{session_id}", tags=["session"])
async def get_public_session(request: Request, session_id: str) -> JSONResponse:
    session = await _resolve_public_session(request, required=True)
    assert session is not None
    if not secrets.compare_digest(session.session_id, session_id):
        raise HTTPException(status_code=404, detail="Public session not found.")
    return JSONResponse(
        content=_public_session_manager(request).response(session).model_dump(mode="json")
    )


@app.post("/v1/session/persona", tags=["session"])
async def transition_public_persona(
    request: Request, body: PersonaTransitionRequest
) -> PersonaTransitionResponse:
    session = await _resolve_public_session(request, required=True)
    assert session is not None
    manager = _public_session_manager(request)
    try:
        manager.require_csrf(session, body.csrf_token)
    except PublicSessionError as exc:
        raise HTTPException(status_code=403, detail="Invalid CSRF proof.") from exc
    manager.transition(session, body.persona)
    await manager.persist(session)
    clearance = {
        "end_user": "PUBLIC",
        "tier1_analyst": "TIER_1",
        "incident_commander": "TIER_2",
        "admin": "ADMIN",
    }[session.persona.value]
    return PersonaTransitionResponse(
        persona=session.persona,
        actor_id=session.actor_id,
        clearance_level=clearance,
        can_approve=session.persona.value in {"incident_commander", "admin"},
    )


@app.post("/v1/session/reset", tags=["session"])
async def reset_public_session(request: Request, body: CsrfProof) -> JSONResponse:
    manager = _public_session_manager(request)
    old_session = await _resolve_public_session(request, required=True)
    assert old_session is not None
    try:
        manager.require_csrf(old_session, body.csrf_token)
    except PublicSessionError as exc:
        raise HTTPException(status_code=403, detail="Invalid CSRF proof.") from exc
    await manager.revoke_remote(old_session)
    session, cookie = manager.create()
    await manager.persist(session)
    payload = PublicSessionResetResponse(
        **manager.response(session).model_dump(), replaced_session=True
    )
    response = JSONResponse(content=payload.model_dump(mode="json"))
    _set_public_cookie(response, cookie)
    return response


def _generation_capability_status(
    expected: str, component: str, observed: str | None
) -> CapabilityStatus:
    if observed == expected:
        return CapabilityStatus(state=CapabilityState.READY)
    return CapabilityStatus(
        state=CapabilityState.DEGRADED,
        detail=f"{component} generation mismatch",
    )


def _inference_capability_status(
    storage: CapabilityStatus,
    *,
    cloud_enabled: bool,
    cloud_model: str,
    local_embedder_ready: bool,
) -> CapabilityStatus:
    inference_ready = bool(cloud_model) if cloud_enabled else local_embedder_ready
    if storage.state == CapabilityState.READY and inference_ready:
        return CapabilityStatus(state=CapabilityState.READY)
    return CapabilityStatus(
        state=CapabilityState.DEGRADED,
        detail="storage or inference configuration unavailable",
    )


async def _probe_runtime_capabilities(request: Request) -> ReadinessResponse:
    timeout = settings.capability_probe_timeout_seconds

    def manifest_generation() -> CapabilityStatus:
        try:
            from src.utils.synthetic_data import load_manifest

            manifest = load_manifest()
            return _generation_capability_status(
                settings.synthetic_dataset_generation, "manifest", manifest.generation
            )
        except Exception:
            return CapabilityStatus(
                state=CapabilityState.DEGRADED,
                detail="manifest unavailable",
            )

    async def groq() -> CapabilityStatus:
        from src.utils.llm_probe import probe_chat_completion

        client: httpx.AsyncClient = request.app.state.http
        ready, detail = await probe_chat_completion(
            client,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            models=[settings.llm_model, settings.llm_fallback_model],
            timeout_seconds=timeout,
        )
        if ready:
            return CapabilityStatus(state=CapabilityState.READY)
        return CapabilityStatus(state=CapabilityState.DEGRADED, detail=detail)

    async def qdrant_storage() -> CapabilityStatus:
        if not settings.qdrant_url or not settings.qdrant_api_key:
            return CapabilityStatus(state=CapabilityState.DEGRADED, detail="not configured")
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            from src.utils.cache import create_async_qdrant_client

            client = create_async_qdrant_client()
            await asyncio.wait_for(client.get_collections(), timeout=timeout)
            active_points = await asyncio.wait_for(
                client.count(
                    collection_name=settings.qdrant_collection_name,
                    count_filter=Filter(
                        must=[
                            FieldCondition(
                                key="collection_version",
                                match=MatchValue(value=settings.knowledge_collection_version),
                            ),
                            FieldCondition(
                                key="dataset_generation",
                                match=MatchValue(value=settings.synthetic_dataset_generation),
                            ),
                        ]
                    ),
                    exact=True,
                ),
                timeout=timeout,
            )
            await client.close()
            if active_points.count < 1:
                return CapabilityStatus(
                    state=CapabilityState.DEGRADED,
                    detail="active knowledge generation unavailable",
                )
            return CapabilityStatus(state=CapabilityState.READY)
        except Exception:
            return CapabilityStatus(state=CapabilityState.DEGRADED, detail="provider unavailable")

    async def redis() -> CapabilityStatus:
        if not settings.redis_url:
            return CapabilityStatus(state=CapabilityState.DEGRADED, detail="not configured")
        try:
            from src.utils.http_client import create_async_redis_client

            client = create_async_redis_client(settings.redis_url, socket_connect_timeout=timeout)
            await asyncio.wait_for(client.ping(), timeout=timeout)
            await client.aclose()
            return CapabilityStatus(state=CapabilityState.READY)
        except Exception:
            return CapabilityStatus(state=CapabilityState.DEGRADED, detail="provider unavailable")

    async def postgres() -> CapabilityStatus:
        if not settings.postgres_sync_url:
            return CapabilityStatus(state=CapabilityState.DEGRADED, detail="not configured")
        try:
            from src.api.orchestrator import app as orchestrator_app

            pool = getattr(orchestrator_app.state, "conn_pool", None)
            if pool is None:
                raise RuntimeError("pool unavailable")

            def check() -> str | None:
                with pool.connection(timeout=timeout) as connection, connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT key, value FROM kraken_runtime_metadata "
                        "WHERE key IN ('synthetic_dataset_generation', 'synthetic_dataset_state')"
                    )
                    metadata = {str(row[0]): str(row[1]) for row in cursor.fetchall()}
                    if metadata.get("synthetic_dataset_state") != "active":
                        return None
                    cursor.execute(
                        "SELECT COUNT(*) FROM tickets WHERE payload->>'dataset_generation' = %s",
                        (settings.synthetic_dataset_generation,),
                    )
                    count_row = cursor.fetchone()
                    if not count_row or int(count_row[0]) < 1:
                        return None
                    return metadata.get("synthetic_dataset_generation")

            observed = await asyncio.wait_for(asyncio.to_thread(check), timeout=timeout)
            return _generation_capability_status(
                settings.synthetic_dataset_generation, "postgres", observed
            )
        except Exception:
            return CapabilityStatus(state=CapabilityState.DEGRADED, detail="provider unavailable")

    groq_state, qdrant_state, redis_state, postgres_state = await asyncio.gather(
        groq(), qdrant_storage(), redis(), postgres()
    )
    from src.api.knowledge import app as knowledge_app

    inference_state = _inference_capability_status(
        qdrant_state,
        cloud_enabled=settings.qdrant_cloud_inference_enabled,
        cloud_model=settings.qdrant_inference_model,
        local_embedder_ready=getattr(knowledge_app.state, "embedder", None) is not None,
    )
    from src.api.orchestrator import app as orchestrator_app

    hitl_checkpoint_state = CapabilityStatus(
        state=(
            CapabilityState.READY
            if postgres_state.state == CapabilityState.READY
            and bool(getattr(orchestrator_app.state, "checkpointer_ready", False))
            else CapabilityState.DEGRADED
        ),
        detail=(
            None
            if bool(getattr(orchestrator_app.state, "checkpointer_ready", False))
            else "managed checkpointer unavailable"
        ),
    )

    async def semantic_cache() -> CapabilityStatus:
        if not settings.semantic_cache_enabled:
            return CapabilityStatus(state=CapabilityState.DISABLED, detail="disabled")
        if (
            qdrant_state.state != CapabilityState.READY
            and redis_state.state != CapabilityState.READY
        ):
            return CapabilityStatus(
                state=CapabilityState.DEGRADED,
                detail="qdrant and redis unavailable",
            )
        try:
            from src.api.orchestrator import app as orchestrator_app
            from src.utils.semantic_cache_policy import cache_context

            cache = getattr(orchestrator_app.state, "semantic_cache", None)
            if cache is None:
                return CapabilityStatus(
                    state=CapabilityState.DEGRADED,
                    detail="cache unavailable",
                )
            context = cache_context({"operator_role": "end_user"}).as_payload()
            vector_dim = (
                settings.qdrant_inference_dim
                if settings.qdrant_url and settings.qdrant_cloud_inference_enabled
                else settings.embedding_dim
            )
            ready, detail = await asyncio.wait_for(
                cache.probe(context, vector_dim),
                timeout=timeout,
            )
            if ready:
                return CapabilityStatus(state=CapabilityState.READY)
            return CapabilityStatus(state=CapabilityState.DEGRADED, detail=detail)
        except Exception as exc:
            return CapabilityStatus(
                state=CapabilityState.DEGRADED,
                detail=exc.__class__.__name__,
            )

    semantic_cache_state = await semantic_cache()
    capabilities = {
        "synthetic_dataset": manifest_generation(),
        "groq": groq_state,
        "qdrant_storage": qdrant_state,
        "qdrant_inference": inference_state,
        "redis": redis_state,
        "postgres": postgres_state,
        "semantic_cache": semantic_cache_state,
        "hitl_checkpoints": hitl_checkpoint_state,
    }
    overall = (
        CapabilityState.READY
        if all(item.state == CapabilityState.READY for item in capabilities.values())
        else CapabilityState.DEGRADED
    )
    return ReadinessResponse(
        status=overall,
        dataset_generation=settings.synthetic_dataset_generation,
        capabilities=capabilities,
    )


@app.get("/ready", tags=["ops"])
async def ready_check(request: Request) -> JSONResponse:
    readiness = await _probe_runtime_capabilities(request)
    status_code = 200 if readiness.status == CapabilityState.READY else 503
    return JSONResponse(status_code=status_code, content=readiness.model_dump(mode="json"))


@app.get("/", tags=["frontend"])
async def root() -> Response:
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(
        {
            "service": "gateway",
            "status": "frontend_not_built",
            "health": "/health",
        }
    )


def _compile_privileged_action_pattern() -> re.Pattern[str]:
    terms = get_privileged_action_terms()
    escaped_terms = [re.escape(term).replace(r"\ ", r"\s+") for term in terms]
    return re.compile(r"\b(" + "|".join(escaped_terms) + r")\b", re.IGNORECASE)


_HIGH_PRIVILEGE_PATTERNS = _compile_privileged_action_pattern()


async def _prepare_agent_request(
    request: Request,
) -> tuple[dict[str, Any] | None, dict[str, str], JSONResponse | None]:
    allowed, rl_headers = await _check_rate_limit(request)
    if not allowed:
        return (
            None,
            rl_headers,
            JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Rate limit exceeded. Try again shortly."},
                headers=rl_headers,
            ),
        )

    try:
        body = await request.json()
    except Exception:
        return (
            None,
            rl_headers,
            JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Invalid JSON body."},
            ),
        )

    if not isinstance(body, dict):
        return (
            None,
            rl_headers,
            JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"error": "Invalid request payload", "details": []},
            ),
        )

    public_session = await _resolve_public_session(request)
    if public_session is not None:
        try:
            _public_session_manager(request).require_csrf(
                public_session, request.headers.get("X-CSRF-Token")
            )
        except PublicSessionError:
            return (
                None,
                rl_headers,
                JSONResponse(status_code=403, content={"error": "Invalid CSRF proof."}),
            )
        user_id = public_session.actor_id
        operator_role = public_session.persona.value
        body["session_id"] = public_session.session_id
    else:
        user_id = getattr(request.state, "user_id", "anonymous")
        operator_role = getattr(request.state, "operator_role", "end_user")
        body.setdefault("session_id", str(uuid.uuid4()))
    body["user_id"] = user_id
    metadata = body.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["execution_id"] = uuid.uuid4().hex
        metadata["operator_role"] = operator_role
        if public_session is not None:
            metadata["public_session_id"] = public_session.session_id
            metadata["actor_id"] = public_session.actor_id
            metadata["has_private_uploads"] = bool(public_session.upload_ids)
            metadata["dataset_generation"] = public_session.dataset_generation

    message = body.get("message", "")
    if isinstance(message, str) and message:
        guard_result = guard_message(message, operator_role)
        if guard_result.blocked:
            log.warning("gateway.prompt_injection_blocked", path=request.url.path)
            return (
                None,
                rl_headers,
                JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": "Request blocked: potential prompt injection detected."},
                ),
            )
        if guard_result.redacted_pii:
            body["message"] = guard_result.sanitized_text
            message = guard_result.sanitized_text

        if _HIGH_PRIVILEGE_PATTERNS.search(message) and not is_operator_role(operator_role):
            log.warning(
                "gateway.privilege_escalation_denied",
                user_id=user_id,
                message_preview=message[:80],
            )
            return (
                None,
                rl_headers,
                JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": (
                            "Access denied. This operation requires operator-level clearance. "
                            "Please contact your security administrator to request elevated access."
                        )
                    },
                ),
            )

    try:
        QueryRequest.model_validate(body)
    except ValidationError as err:
        return (
            None,
            rl_headers,
            JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error": "Invalid request payload",
                    "details": err.errors(include_url=False),
                },
            ),
        )

    return body, rl_headers, None


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
    body, rl_headers, error_response = await _prepare_agent_request(request)
    if error_response is not None:
        return error_response
    assert body is not None

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
    body, rl_headers, error_response = await _prepare_agent_request(request)
    if error_response is not None:
        return error_response
    assert body is not None

    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    forward_headers = service_headers(trace_id=request_id)
    forward_headers.update(
        {
            "X-Request-Id": request_id,
            "Content-Type": "application/json",
        }
    )

    async def stream_generator():
        is_mock_http = type(getattr(request.app.state, "http", None)).__name__ in (
            "MagicMock",
            "AsyncMock",
            "Mock",
        )
        target_app = None if is_mock_http else get_in_process_app_for_url(settings.orchestrator_url)
        if target_app is not None:
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=target_app),
                    base_url="http://internal",
                    timeout=120.0,
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


@app.get("/v1/session/status", tags=["session"])
async def public_run_status(request: Request) -> JSONResponse:
    """Return session-owned execution state without re-running the agent."""
    session = await _resolve_public_session(request, required=True)
    assert session is not None
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    try:
        response = await internal_request(
            "GET",
            f"{settings.orchestrator_url}/status/{session.session_id}",
            headers=service_headers(trace_id=request_id),
        )
        return JSONResponse(
            content=response.json(),
            status_code=response.status_code,
            headers={"X-Request-Id": request_id},
        )
    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            status_code=exc.response.status_code,
            content={"error": "Execution status is unavailable."},
            headers={"X-Request-Id": request_id},
        )
    except Exception as exc:
        log.error("gateway.status_proxy_failed", error=exc.__class__.__name__)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Execution status is temporarily unavailable."},
            headers={"X-Request-Id": request_id},
        )


# HITL approval proxy routes (single-port browser flow)
@app.get("/approve/{approval_id}/details", tags=["hitl"])
async def approval_details_proxy(request: Request, approval_id: str) -> JSONResponse:
    """Proxy approval details + CSRF token to the in-process approval app."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    url = f"{settings.approval_url}/approve/{approval_id}/details"
    try:
        resp = await internal_request("GET", url, headers={"X-Request-Id": request_id})
        content = resp.json()
        session = await _resolve_public_session(request, required=True)
        assert session is not None
        if content.get("session_id") != session.session_id:
            return JSONResponse(status_code=404, content={"detail": "Approval request not found."})
        return JSONResponse(
            content=content,
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
    session = await _resolve_public_session(request, required=True)
    assert session is not None
    form = await request.form()
    try:
        _public_session_manager(request).require_csrf(
            session, str(form.get("session_csrf_token") or "")
        )
    except PublicSessionError as exc:
        raise HTTPException(status_code=403, detail="Invalid CSRF proof.") from exc

    body = urlencode(
        {
            "decision": str(form.get("decision") or ""),
            "csrf_token": str(form.get("csrf_token") or ""),
            "approver_role": session.persona.value,
            "approver_id": session.actor_id,
            "expected_session_id": session.session_id,
        }
    ).encode("ascii")
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
            headers={
                "Content-Type": content_type,
                "Accept": "application/json",
                "X-Request-Id": request_id,
            },
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
    """Validate and ingest a private, expiring synthetic-environment document."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    session = await _resolve_public_session(request, required=True)
    assert session is not None
    try:
        _public_session_manager(request).require_csrf(session, request.headers.get("X-CSRF-Token"))
    except PublicSessionError as exc:
        raise HTTPException(status_code=403, detail="Invalid CSRF proof.") from exc

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".txt", ".md", ".markdown"}:
        return JSONResponse(
            status_code=415,
            content={"error": "Only PDF, TXT, and Markdown files are accepted."},
        )
    if len(session.upload_ids) >= settings.public_upload_max_files:
        return JSONResponse(
            status_code=429,
            content={"error": "This public session already has three active uploads."},
        )
    headers = service_headers(trace_id=request_id)
    try:
        content_bytes = await file.read(settings.public_upload_max_bytes + 1)
        if len(content_bytes) > settings.public_upload_max_bytes:
            return JSONResponse(
                status_code=413,
                content={"error": "Upload exceeds the 2 MB public-session limit."},
            )
        if suffix == ".pdf" and not content_bytes.startswith(b"%PDF-"):
            return JSONResponse(status_code=415, content={"error": "Invalid PDF file."})
        if suffix != ".pdf":
            if b"\x00" in content_bytes:
                return JSONResponse(status_code=415, content={"error": "Invalid text file."})
            try:
                content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return JSONResponse(
                    status_code=415, content={"error": "Text uploads must use UTF-8."}
                )
        if not content_bytes.strip():
            return JSONResponse(status_code=422, content={"error": "The uploaded file is empty."})
        files = {"file": (file.filename, content_bytes, file.content_type)}
        data = {
            "allowed_roles": allowed_roles,
            "public_session_id": session.session_id,
            "expires_at": str(session.expires_at),
        }
        resp = await internal_request(
            "POST",
            f"{settings.knowledge_url}/upload",
            files=files,
            data=data,
            headers=headers,
            timeout_seconds=60.0,
        )
        result = resp.json()
        session.upload_ids.add(uuid.uuid4().hex)
        await _public_session_manager(request).persist(session)
        return JSONResponse(
            content=result,
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
        log.error("gateway.upload_proxy_failed", error=exc.__class__.__name__)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "Upload processing is temporarily unavailable."},
            headers={"X-Request-Id": request_id},
        )


@app.post("/v1/report/export", tags=["report"])
async def export_report(request: Request) -> Response:
    """
    Generate and export a formatted Executive Incident Briefing HTML report for a session.
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


# Audit proxy routes
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


@app.api_route(
    "/{unknown_path:path}",
    methods=["POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def unknown_mutation_route(unknown_path: str) -> None:
    del unknown_path
    raise HTTPException(status_code=404, detail="Not found.")


@app.get("/{browser_path:path}", include_in_schema=False)
async def spa_fallback(browser_path: str) -> Response:
    """Serve compiled assets and React deep links after every API route is registered."""
    if browser_path.split("/", 1)[0] in {"v1", "approve", "health", "ready", "metrics"}:
        raise HTTPException(status_code=404, detail="Not found.")
    if not FRONTEND_DIST.is_dir():
        raise HTTPException(status_code=404, detail="Frontend is not built.")

    candidate = (FRONTEND_DIST / browser_path).resolve()
    if FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(FRONTEND_DIST / "index.html")

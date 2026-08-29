from __future__ import annotations

import asyncio
import contextlib
import sys
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Literal

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from langgraph.types import Command

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    AsyncPostgresSaver = None  # type: ignore[assignment, misc]

try:
    from psycopg_pool import ConnectionPool
except ImportError:
    ConnectionPool = None  # type: ignore[assignment, misc]
try:
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row
except ImportError:
    AsyncConnection = None  # type: ignore[assignment, misc]
    dict_row = None  # type: ignore[assignment]
from pydantic import BaseModel, Field

from src.agent.agent import build_graph_async
from src.utils.auth import verify_service_token
from src.utils.cache import SemanticCache
from src.utils.config import get_settings
from src.utils.db import create_sync_pool
from src.utils.http_client import (
    create_async_http_client,
    internal_request,
    metrics_text,
    service_headers,
)
from src.utils.llm import validate_llm_config
from src.utils.logging import configure_logging
from src.utils.middleware.trace_id import TraceIdMiddleware
from src.utils.models.agent import QueryRequest, QueryResponse
from src.utils.observability import flush_langfuse, get_langfuse_callback_handler
from src.utils.semantic_cache_policy import cache_context, cache_query, is_cache_eligible

log = structlog.get_logger(__name__)
settings = get_settings()


async def _open_async_checkpointer() -> tuple[Any, Any]:
    """Open a PgBouncer-safe LangGraph saver and apply its migrations."""
    if AsyncPostgresSaver is None or AsyncConnection is None or dict_row is None:
        raise RuntimeError("Postgres checkpointer dependencies are unavailable.")
    connection = await AsyncConnection.connect(
        settings.postgres_sync_url,
        autocommit=True,
        prepare_threshold=None,
        row_factory=dict_row,
    )
    try:
        saver = AsyncPostgresSaver(connection)
        await saver.setup()
        return saver, connection
    except Exception:
        await connection.close()
        raise


# Typed request schema for the callback endpoint
class ApprovalCallbackRequest(BaseModel):
    approval_id: str = Field(..., description="UUID issued by executor when HITL fired.")
    decision: Literal["approve", "reject"] = Field(
        ..., description="Human decision. Only 'approve' or 'reject' are valid."
    )
    session_id: str | None = Field(
        default=None, description="Target session_id associated with the approval request."
    )
    approver_role: str | None = Field(
        default=None, description="Role of the human operator authorizing the execution."
    )
    approver_id: str | None = Field(
        default=None, description="User identifier of the human operator authorizing the execution."
    )


# Reaper background task
async def _reaper_loop(app: FastAPI) -> None:
    """
    Periodically prunes stale LangGraph checkpoints to prevent DB bloat.
    Approval timeouts are managed centrally by Redis TTL in ApprovalQueue.
    """
    loop_count = 0
    while True:
        await asyncio.sleep(60)
        loop_count += 1
        try:
            pool = getattr(app.state, "conn_pool", None)
            if pool is not None and loop_count % 30 == 0:
                prune_stale_checkpoints(pool)
        except Exception as exc:
            log.error("reaper.loop_error", error=str(exc))


def prune_stale_checkpoints(pool: ConnectionPool | None) -> dict[str, int]:
    """
    Safely delete stale checkpoints from PostgreSQL for timed-out or inactive sessions.
    Prevents database bloat over time.
    """
    deleted_counts = {"checkpoints": 0, "checkpoint_writes": 0}
    if not pool:
        return deleted_counts
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            # 1. Prune checkpoints & writes for timed-out approvals older than 1 hour
            cur.execute(
                """
                WITH stale AS (
                    SELECT session_id
                    FROM approval_map
                    WHERE status = 'timeout' AND resolved_at < NOW() - INTERVAL '1 hour'
                )
                DELETE FROM checkpoint_writes
                WHERE thread_id IN (SELECT session_id FROM stale);
                """
            )
            deleted_counts["checkpoint_writes"] += cur.rowcount

            cur.execute(
                """
                WITH stale AS (
                    SELECT session_id
                    FROM approval_map
                    WHERE status = 'timeout' AND resolved_at < NOW() - INTERVAL '1 hour'
                )
                DELETE FROM checkpoints
                WHERE thread_id IN (SELECT session_id FROM stale);
                """
            )
            deleted_counts["checkpoints"] += cur.rowcount

            # 2. Demo checkpoints are temporary even when no approval row exists.
            cur.execute(
                """
                WITH inactive AS (
                    SELECT thread_id
                    FROM checkpoints
                    GROUP BY thread_id
                    HAVING MAX(NULLIF(checkpoint->>'ts', '')::timestamptz)
                        < NOW() - INTERVAL '1 hour'
                )
                DELETE FROM checkpoint_writes
                WHERE thread_id IN (SELECT thread_id FROM inactive);
                """
            )
            deleted_counts["checkpoint_writes"] += cur.rowcount

            cur.execute(
                """
                WITH inactive AS (
                    SELECT thread_id
                    FROM checkpoints
                    GROUP BY thread_id
                    HAVING MAX(NULLIF(checkpoint->>'ts', '')::timestamptz)
                        < NOW() - INTERVAL '1 hour'
                )
                DELETE FROM checkpoints
                WHERE thread_id IN (SELECT thread_id FROM inactive);
                """
            )
            deleted_counts["checkpoints"] += cur.rowcount

            log.info("reaper.pruned_stale_checkpoints", **deleted_counts)
    except Exception as exc:
        log.error("reaper.prune_error", error=str(exc))

    return deleted_counts


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="orchestrator"
    )
    log.info("orchestrator.startup", model=settings.llm_model)

    # 1. Validate LLM key configuration (log warning if unconfigured so orchestrator boots cleanly)
    try:
        validate_llm_config()
    except Exception as exc:
        log.warning("orchestrator.llm_unconfigured", error=str(exc))

    # 2. Open a sync psycopg connection pool for PostgresSaver if configured
    conn_pool = None
    if ConnectionPool is not None and settings.postgres_sync_url:
        conn_pool = create_sync_pool(
            settings.postgres_sync_url,
            min_size=1,
            max_size=10,
            max_idle=settings.postgres_max_idle_time,
            connect_kwargs={
                "keepalives": settings.postgres_keepalives,
                "keepalives_idle": settings.postgres_keepalives_idle,
                "keepalives_interval": settings.postgres_keepalives_interval,
                "keepalives_count": settings.postgres_keepalives_count,
            },
        )
        if conn_pool is None:
            log.warning(
                "orchestrator.postgres_pool_failed",
                error="shared sync pool creation returned None",
            )
    app.state.conn_pool = conn_pool

    # 4. Build the compiled graph (AsyncPostgresSaver with MemorySaver fallback)
    saver_connection = None
    app.state.checkpointer_ready = False
    if AsyncPostgresSaver is not None and settings.postgres_sync_url:
        try:
            saver, saver_connection = await _open_async_checkpointer()
            app.state.saver_connection = saver_connection
            app.state.agent_graph = await build_graph_async(saver)
            app.state.checkpointer_ready = True
            log.info("orchestrator.async_checkpointer_ready")
        except Exception as exc:
            log.warning("orchestrator.async_checkpointer_failed", error=exc.__class__.__name__)
            saver_connection = None

    if saver_connection is None:
        app.state.saver_connection = None
        app.state.agent_graph = await build_graph_async(None)
        log.info("orchestrator.memory_checkpointer_ready")

    log.info("orchestrator.graph_ready")

    # 5. Start the reaper background task
    reaper_task = asyncio.create_task(_reaper_loop(app))
    log.info("orchestrator.reaper_started")

    # 6. Initialize concurrency semaphore
    semaphore = asyncio.Semaphore(settings.orchestrator_max_concurrency)
    from src.utils.cache import SemanticCache

    app.state.graph_semaphore = semaphore
    app.state.is_shutting_down = False
    app.state.http = create_async_http_client()

    app.state.semantic_cache = SemanticCache()
    await app.state.semantic_cache.init()  # async collection setup — does not block event loop

    yield

    # Shutdown
    app.state.is_shutting_down = True
    log.info("orchestrator.draining_in_flight_tasks")
    if semaphore:
        for _ in range(settings.orchestrator_max_concurrency):
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(semaphore.acquire(), timeout=5.0)

    await app.state.http.aclose()
    reaper_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reaper_task

    if getattr(app.state, "saver_connection", None):
        with contextlib.suppress(Exception):
            await app.state.saver_connection.close()

    if getattr(app.state, "conn_pool", None):
        with contextlib.suppress(Exception):
            app.state.conn_pool.close()

    flush_langfuse()
    log.info("orchestrator.shutdown")


# App

app = FastAPI(
    title="KRAKEN Orchestrator",
    description="LangGraph Agent Orchestrator — Xiarch Cybersecurity Consultancy",
    version="0.5.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)


@app.get("/metrics", tags=["ops"])
async def metrics() -> PlainTextResponse:
    """Prometheus metrics endpoint for scraped orchestrator metrics."""
    return PlainTextResponse(content=metrics_text("orchestrator"))


def _graph_config(
    session_id: str,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """LangGraph thread config — all checkpointed state lives under this key."""
    trace_tags = list(tags) if tags else ["kraken-agent"]
    if settings.environment and settings.environment not in trace_tags:
        trace_tags.append(settings.environment)

    trace_meta = {
        "langfuse_session_id": session_id,
        "langfuse_user_id": user_id or "anonymous",
        "langfuse_trace_name": "kraken-agent-run",
        "langfuse_tags": trace_tags,
        **(metadata or {}),
    }

    cfg: dict[str, Any] = {
        "configurable": {"thread_id": session_id},
        "tags": trace_tags,
        "metadata": trace_meta,
    }
    callbacks = get_langfuse_callback_handler()
    if callbacks:
        cfg["callbacks"] = callbacks
    return cfg


# Health
@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    """Liveness probe. Checks connectivity to the Postgres saver pool."""
    db_ok = False
    pool: ConnectionPool | None = getattr(app.state, "conn_pool", None)
    if pool is not None:
        try:
            with pool.connection() as conn:
                conn.execute("SELECT 1;")
            db_ok = True
        except Exception as exc:
            log.error("orchestrator.health_db_check_failed", error=str(exc))

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "orchestrator",
        "database": db_ok,
    }


async def _fetch_session_messages(
    session_id: str, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Fetch existing short-term session conversation messages from Memory Service."""
    url = f"{settings.memory_url}/session/{session_id}"
    headers = service_headers()
    try:
        resp = await internal_request("GET", url, headers=headers, client=client)
        data = resp.json()
        return data.get("messages", [])
    except Exception as exc:
        log.warning(
            "orchestrator.fetch_session_memory_failed", session_id=session_id, error=str(exc)
        )
    return []


def _initial_state(body: QueryRequest, session_messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the initial graph state shared by /run and /run/stream."""
    return {
        "session_id": body.session_id,
        "user_id": body.user_id,
        "operator_role": body.metadata.get("operator_role", "end_user"),
        "demo_session_id": body.metadata.get("demo_session_id", ""),
        "demo_actor_id": body.metadata.get("actor_id", ""),
        "execution_id": body.metadata.get("execution_id", ""),
        "user_message": body.message,
        "messages": session_messages,
        "selected_action": None,
        "selected_actions": None,
        "action_payload": None,
        "risk_level": None,
        "approval_id": None,
        "approval_status": None,
        "action_result": None,
        "evidence": None,
        "error": None,
    }


async def _clear_stale_interrupt(graph: Any, config: dict, session_id: str) -> None:
    """Clear a stale HITL interrupt by resuming the graph with a 'reject' decision.

    This avoids invoking responder_node on the stale query state.
    """
    log.info(
        "orchestrator.clearing_stale_hitl_interrupt",
        session_id=session_id,
        reason="new_message_on_interrupted_session",
    )
    try:
        await graph.ainvoke(
            Command(resume={"decision": "reject"}),
            config,
        )
    except Exception as exc:
        log.warning("orchestrator.stale_hitl_clear_failed", session_id=session_id, error=str(exc))


async def _get_graph(
    session_id: str,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[Any, dict]:
    """
    Return the compiled graph and its LangGraph config for a given session_id.

    If the Postgres async checkpointer connection has been dropped (Supabase idle
    timeout / PgBouncer reset), rebuild the graph with MemorySaver so requests
    always succeed rather than crashing with psycopg.OperationalError.
    """
    graph = getattr(app.state, "agent_graph", None)
    if graph is None:
        log.info("orchestrator.lazy_graph_init")
        app.state.agent_graph = await build_graph_async(None)
        graph = app.state.agent_graph

    config = _graph_config(
        session_id=session_id,
        user_id=user_id,
        tags=tags,
        metadata=metadata,
    )

    # Quick liveness probe: try aget_state and catch a dead connection.
    try:
        await graph.aget_state(config)
        return graph, config
    except Exception as exc:
        err_str = str(exc).lower()
        is_conn_error = any(
            kw in err_str
            for kw in (
                "connection is closed",
                "connection closed",
                "server closed",
                "consuming input failed",
                "prepared statement",
            )
        )
        if not is_conn_error:
            # Non-connection error — let the caller deal with it.
            raise

    # Connection is dead: rebuild graph with MemorySaver fallback
    log.warning("orchestrator.checkpointer_reconnect", session_id=session_id)
    try:
        # Try to teardown the old saver context cleanly
        old_saver_connection = getattr(app.state, "saver_connection", None)
        if old_saver_connection is not None:
            with contextlib.suppress(Exception):
                await old_saver_connection.close()
            app.state.saver_connection = None

        # Attempt reconnection
        if AsyncPostgresSaver is not None and settings.postgres_sync_url:
            new_saver, new_connection = await _open_async_checkpointer()
            app.state.saver_connection = new_connection
            app.state.agent_graph = await build_graph_async(new_saver)
            app.state.checkpointer_ready = True
            log.info("orchestrator.checkpointer_reconnected")
        else:
            raise RuntimeError("No postgres_sync_url configured for reconnect")
    except Exception as reconnect_exc:
        log.warning(
            "orchestrator.checkpointer_reconnect_failed_fallback_memory",
            error=str(reconnect_exc),
        )
        app.state.saver_connection = None
        app.state.checkpointer_ready = False
        app.state.agent_graph = await build_graph_async(None)

    graph = app.state.agent_graph
    config = _graph_config(
        session_id=session_id,
        user_id=user_id,
        tags=tags,
        metadata=metadata,
    )
    return graph, config


async def _semantic_cache_lookup(
    body: QueryRequest,
) -> tuple[QueryResponse | None, Any | None, dict[str, str] | None]:
    cache: SemanticCache | None = getattr(app.state, "semantic_cache", None)
    if not cache or not is_cache_eligible(body.message, body.metadata):
        return None, None, None
    context = cache_context(body.metadata).as_payload()
    try:
        query = await cache_query(body.message)
        try:
            cached = await cache.get(query, context, query_text=body.message)
        except TypeError:
            cached = await cache.get(query, context)
        if not cached:
            return None, query, context
        response = QueryResponse.model_validate(cached)
        if _is_provider_unavailable_response(response):
            log.warning("orchestrator.semantic_cache_ignored_provider_fallback")
            return None, query, context
        response.session_id = body.session_id
        response.trace_id = str(uuid.uuid4())
        response.cache.hit = True
        response.cache.scope = context["scope"]
        response.cache.embedding_model = context["embedding_model"]
        response.cache.knowledge_version = context["knowledge_version"]
        return response, query, context
    except Exception as exc:
        log.warning("orchestrator.semantic_cache_lookup_failed", error=exc.__class__.__name__)
        return None, None, context


async def _semantic_cache_store(
    body: QueryRequest,
    response: QueryResponse,
    query: Any | None,
    context: dict[str, str] | None,
) -> None:
    cache: SemanticCache | None = getattr(app.state, "semantic_cache", None)
    if not cache or not context or not is_cache_eligible(body.message, body.metadata):
        return
    if response.action_taken not in (None, "auto_respond") or not response.retrieved_chunks:
        return
    if _is_provider_unavailable_response(response):
        log.warning("orchestrator.semantic_cache_skip_provider_fallback")
        return
    try:
        resolved_query = query if query is not None else await cache_query(body.message)
        response.cache.hit = False
        response.cache.scope = context["scope"]
        response.cache.embedding_model = context["embedding_model"]
        response.cache.knowledge_version = context["knowledge_version"]
        await cache.put(
            resolved_query,
            body.message,
            response.model_dump(mode="json"),
            context,
        )
    except Exception as exc:
        log.warning("orchestrator.semantic_cache_put_failed", error=exc.__class__.__name__)


def _is_provider_unavailable_response(response: QueryResponse) -> bool:
    text = f"{response.answer}\n{response.reasoning}".lower()
    blocked_markers = (
        "ai provider is temporarily unavailable",
        "provider is temporarily unavailable",
        "provider could not complete",
        "llm_provider_unavailable",
    )
    return any(marker in text for marker in blocked_markers)


# /run
@app.post("/run", tags=["agent"])
async def run(body: QueryRequest) -> Any:
    """
    Execute the agent graph for a user query.
    Returns QueryResponse on completion, or pending_approval dict on HITL pause.
    """
    log.info("orchestrator.run", session_id=body.session_id, user_id=body.user_id)

    # _get_graph() returns a healthy (graph, config) pair — auto-reconnects if
    # the Postgres async connection was dropped by Supabase's idle timeout.
    try:
        graph, config = await _get_graph(
            session_id=body.session_id,
            user_id=body.user_id,
            tags=["kraken-agent", "sync-run"],
            metadata={"endpoint": "/run", "user_id": body.user_id},
        )
    except Exception as exc:
        trace_id = str(uuid.uuid4())
        log.error("orchestrator.graph_init_failed", error=exc.__class__.__name__, trace_id=trace_id)
        raise HTTPException(
            status_code=503,
            detail={"code": "agent_unavailable", "trace_id": trace_id},
        ) from exc

    # Check if session is already completed or currently paused
    snapshot = await graph.aget_state(config)
    clean_msg = body.message.strip().lower() if body.message else ""
    if not clean_msg or clean_msg in ("", ".", "check status", "check approval status"):
        if snapshot.values and "final_answer" in snapshot.values and not snapshot.next:
            log.info("orchestrator.status_check_completed", session_id=body.session_id)
            return _build_response(body.session_id, snapshot.values)
        if snapshot.next:
            interrupt_val = _extract_interrupt(snapshot)
            approval_id = interrupt_val.get("approval_id")
            return {
                "status": "pending_approval",
                "approval_id": approval_id,
                "session_id": body.session_id,
                "message": "A CRITICAL triage action requires human approval. Check the approval service.",
            }

    # If session is stuck in a HITL interrupt, clear it without invoking
    # responder_node on the stale query state.
    if snapshot.next:
        await _clear_stale_interrupt(graph, config, body.session_id)
        snapshot = await graph.aget_state(config)

    http_client: httpx.AsyncClient | None = getattr(app.state, "http", None)

    cached_response, cache_query_value, cache_scope = await _semantic_cache_lookup(body)
    if cached_response is not None:
        log.info("orchestrator.semantic_cache_hit", session_id=body.session_id)
        return cached_response

    session_messages = await _fetch_session_messages(body.session_id, client=http_client)

    initial_state = _initial_state(body, session_messages)

    # If session is stuck in a HITL interrupt, clear it when a new message arrives
    if body.message:
        try:
            snapshot = await graph.aget_state(config)
            if snapshot.next:
                await _clear_stale_interrupt(graph, config, body.session_id)
        except Exception as exc:
            log.warning("orchestrator.run_stale_hitl_clear_failed", error=str(exc))

    if getattr(app.state, "is_shutting_down", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server shutting down.",
        )

    # Check concurrency limit — atomic acquire with timeout=0 prevents TOCTOU race
    semaphore: asyncio.Semaphore | None = getattr(app.state, "graph_semaphore", None)

    if semaphore:
        # semaphore.locked() is True when value == 0 (no slots available).
        # No await between the check and acquire, so no TOCTOU risk in the
        # single-threaded asyncio event loop.
        if semaphore.locked():
            log.warning("orchestrator.concurrency_limit_reached", session_id=body.session_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server busy: maximum concurrent agent executions reached. Please try again shortly.",
            )
        await semaphore.acquire()

    try:
        # Async graph invocation
        result = await graph.ainvoke(initial_state, config)
    except Exception as exc:
        trace_id = str(uuid.uuid4())
        log.error("orchestrator.run_error", error=exc.__class__.__name__, trace_id=trace_id)
        raise HTTPException(
            status_code=503,
            detail={"code": "agent_unavailable", "trace_id": trace_id},
        ) from exc
    finally:
        if semaphore:
            semaphore.release()

    # Check if graph paused for HITL
    snapshot = await graph.aget_state(config)
    if snapshot.next:
        interrupt_val = _extract_interrupt(snapshot)

        approval_id = interrupt_val.get("approval_id", str(uuid.uuid4()))
        action_name = interrupt_val.get("action_name", "unknown")

        log.info(
            "orchestrator.hitl_paused",
            session_id=body.session_id,
            approval_id=approval_id,
            action=action_name,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "session_id": body.session_id,
            "message": "A CRITICAL triage action requires human approval. Check the approval service.",
        }

    response = _build_response(body.session_id, result)
    await _semantic_cache_store(body, response, cache_query_value, cache_scope)
    return response


# /run/stream
@app.post("/run/stream", tags=["agent"])
async def run_stream(body: QueryRequest) -> StreamingResponse:
    """
    Execute the agent graph and stream LangGraph node execution events
    to the client via Server-Sent Events (SSE).
    Each event carries: {node, status, elapsed_ms} JSON.
    A ':ping' comment is sent every 15 s to keep Render free-tier connections alive.
    """
    # _get_graph() returns a healthy (graph, config) pair — auto-reconnects if
    # the Postgres async connection was dropped by Supabase's idle timeout.
    try:
        graph, config = await _get_graph(
            session_id=body.session_id,
            user_id=body.user_id,
            tags=["kraken-agent", "stream-run"],
            metadata={"endpoint": "/run/stream", "user_id": body.user_id},
        )
    except Exception as exc:
        trace_id = str(uuid.uuid4())
        log.error(
            "orchestrator.stream_graph_init_failed",
            error=exc.__class__.__name__,
            trace_id=trace_id,
        )

        # Return an SSE error event rather than a hard 500
        async def _err_gen() -> AsyncGenerator[str, None]:
            import json

            yield f"data: {json.dumps({'node': 'error', 'status': 'error', 'message': 'Agent startup is temporarily unavailable.', 'trace_id': trace_id})}\n\n"

        return StreamingResponse(
            _err_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # If session is stuck in a HITL interrupt, clear it without invoking
    # responder_node on the stale query state.
    try:
        snapshot = await graph.aget_state(config)
        if snapshot.next:
            await _clear_stale_interrupt(graph, config, body.session_id)
    except Exception as exc:
        log.warning("orchestrator.stream_stale_hitl_clear_failed", error=str(exc))

    async def event_generator() -> AsyncGenerator[str, None]:
        import json
        import time

        start = time.monotonic()
        last_ping = start

        cached_response, cache_query_value, cache_scope = await _semantic_cache_lookup(body)
        if cached_response is not None:
            yield (
                "data: "
                + json.dumps({"node": "semantic_cache", "status": "cache_hit", "elapsed_ms": 0})
                + "\n\n"
            )
            yield (
                "data: "
                + json.dumps(
                    {
                        "node": "done",
                        "status": "end",
                        "elapsed_ms": 0,
                        "response": cached_response.model_dump(mode="json"),
                    }
                )
                + "\n\n"
            )
            return

        # Fetch session history so the graph has conversation context
        http_client: httpx.AsyncClient | None = getattr(app.state, "http", None)
        session_messages = await _fetch_session_messages(body.session_id, client=http_client)

        initial_state = _initial_state(body, session_messages)

        try:
            async for event in graph.astream_events(  # type: ignore[attr-defined]
                initial_state,
                config=config,
                version="v2",
            ):
                now = time.monotonic()
                # Send ping every 15 s to prevent proxy/Render timeout
                if now - last_ping >= 15:
                    yield ": ping\n\n"
                    last_ping = now

                kind = event.get("event", "")
                name = event.get("name", "")
                if not name or name in ("LangGraph", ""):
                    continue
                if kind == "on_chain_start":
                    payload = json.dumps(
                        {"node": name, "status": "start", "elapsed_ms": round((now - start) * 1000)}
                    )
                    yield f"data: {payload}\n\n"
                elif kind == "on_chain_end":
                    payload = json.dumps(
                        {
                            "node": name,
                            "status": "end",
                            "elapsed_ms": round((now - start) * 1000),
                        }
                    )
                    yield f"data: {payload}\n\n"

            snapshot = await graph.aget_state(config)
            extra_done = {}
            if snapshot.next:
                interrupt_val = _extract_interrupt(snapshot)
                approval_id = interrupt_val.get("approval_id", str(uuid.uuid4()))
                action_name = interrupt_val.get("action_name", "unknown")

                log.info(
                    "orchestrator.hitl_paused",
                    session_id=body.session_id,
                    approval_id=approval_id,
                    action=action_name,
                )

                hitl_payload = json.dumps(
                    {
                        "node": "interrupt",
                        "status": "pending_approval",
                        "elapsed_ms": round((time.monotonic() - start) * 1000),
                        "response": {
                            "status": "pending_approval",
                            "approval_id": approval_id,
                            "session_id": body.session_id,
                            "message": "A CRITICAL triage action requires human approval. Check the approval service.",
                        },
                    }
                )
                yield f"data: {hitl_payload}\n\n"
            elif snapshot.values:
                response = _build_response(body.session_id, snapshot.values)
                await _semantic_cache_store(body, response, cache_query_value, cache_scope)
                extra_done = {"response": response.model_dump(mode="json")}

            done_payload = json.dumps(
                {
                    "node": "done",
                    "status": "end",
                    "elapsed_ms": round((time.monotonic() - start) * 1000),
                    **extra_done,
                }
            )
            yield f"data: {done_payload}\n\n"

        except Exception as exc:
            trace_id = str(uuid.uuid4())
            log.error(
                "orchestrator.stream_error",
                session_id=body.session_id,
                error=exc.__class__.__name__,
                trace_id=trace_id,
            )
            err_payload = json.dumps(
                {
                    "node": "error",
                    "status": "error",
                    "message": "Agent processing is temporarily unavailable.",
                    "trace_id": trace_id,
                }
            )
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/status/{session_id}", tags=["agent"])
async def run_status(
    session_id: str,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any] | QueryResponse:
    """Read the current graph state without invoking or resuming the graph."""
    graph, config = await _get_graph(session_id=session_id, tags=["kraken-agent", "status"])
    snapshot = await graph.aget_state(config)
    if snapshot.next:
        interrupt_value = _extract_interrupt(snapshot)
        return {
            "status": "pending_approval",
            "approval_id": interrupt_value.get("approval_id", ""),
            "session_id": session_id,
            "message": "A CRITICAL triage action requires human approval.",
        }
    values = snapshot.values or {}
    if values and any(
        values.get(key) is not None
        for key in ("final_answer", "action_result", "error", "selected_action")
    ):
        return _build_response(session_id, values)
    return {"status": "running", "session_id": session_id}


@app.post("/approval-callback", tags=["hitl"])
async def approval_callback(
    body: ApprovalCallbackRequest,
    _token: str = Depends(verify_service_token),
) -> Any:
    """
    Resume a paused graph after human approves or rejects a CRITICAL action.
    Called by the approval service with a valid X-Service-Token header.
    """
    log.info(
        "orchestrator.callback_received",
        approval_id=body.approval_id,
        decision=body.decision,
        session_id=body.session_id,
    )

    session_id = body.session_id
    if not session_id:
        # Fallback: check Redis/ApprovalQueue if session_id was omitted
        queue = getattr(app.state, "approval_queue", None)
        if queue:
            entry = await queue.get(body.approval_id)
            if entry:
                session_id = entry.get("session_id")

    if not session_id:
        log.warning("orchestrator.callback_not_found", approval_id=body.approval_id)
        raise HTTPException(status_code=404, detail="Approval ID not found.")

    # Acquire bounded semaphore — same guard as /run
    semaphore: asyncio.Semaphore | None = getattr(app.state, "graph_semaphore", None)
    if semaphore:
        if semaphore.locked():
            log.warning(
                "orchestrator.callback_concurrency_limit_reached",
                approval_id=body.approval_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server busy: maximum concurrent agent executions reached. Retry the callback.",
            )
        await semaphore.acquire()

    graph = app.state.agent_graph
    config = _graph_config(
        session_id=session_id,
        user_id=body.approver_id,
        tags=["kraken-agent", "hitl-resume", body.decision],
        metadata={
            "approval_id": body.approval_id,
            "decision": body.decision,
            "approver_role": body.approver_role,
        },
    )

    try:
        snapshot = await graph.aget_state(config)
        if not snapshot.next:
            raise HTTPException(status_code=409, detail="Approval is no longer pending.")
        interrupt_value = _extract_interrupt(snapshot)
        if interrupt_value.get("approval_id") != body.approval_id:
            raise HTTPException(
                status_code=409, detail="Approval does not match the pending action."
            )
        log.info(
            "orchestrator.resuming",
            session_id=session_id,
            approval_id=body.approval_id,
            decision=body.decision,
            approver_role=body.approver_role,
            approver_id=body.approver_id,
        )
        result = await graph.ainvoke(
            Command(
                resume={
                    "decision": body.decision,
                    "approver_role": body.approver_role,
                    "approver_id": body.approver_id,
                }
            ),
            config,
        )
    except HTTPException:
        raise
    except Exception as exc:
        trace_id = str(uuid.uuid4())
        log.error("orchestrator.resume_error", error=exc.__class__.__name__, trace_id=trace_id)
        raise HTTPException(
            status_code=503,
            detail={"code": "resume_unavailable", "trace_id": trace_id},
        ) from exc
    finally:
        if semaphore:
            semaphore.release()

    return _build_response(session_id, result)


@app.post("/maintenance/prune-checkpoints", status_code=status.HTTP_200_OK)
async def trigger_prune_checkpoints(
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Manually trigger stale PostgreSQL checkpoint pruning."""
    deleted = prune_stale_checkpoints(app.state.conn_pool)
    return {"status": "success", "deleted": deleted}


# Helper
def _extract_interrupt(snapshot: Any) -> dict[str, Any]:
    """Extract the first interrupt value dict from a LangGraph StateSnapshot."""
    for task in getattr(snapshot, "tasks", []):
        for interrupt in getattr(task, "interrupts", []):
            val = getattr(interrupt, "value", {})
            if isinstance(val, dict):
                return val
    return {}


def _build_response(
    session_id: str, state: dict[str, Any], trace_id: str | None = None
) -> QueryResponse:
    """Convert final graph state into a QueryResponse with a unique execution trace ID."""
    selected_action = state.get("selected_action")
    is_auto_respond = not selected_action or selected_action == "auto_respond"

    formatted_chunks = []
    if is_auto_respond:
        raw_chunks = state.get("retrieved_chunks", [])
        for c in raw_chunks[:5]:
            score = float(c.get("relevance_score", 0.0))
            if score < 0.40:
                continue
            meta = c.get("metadata", {})
            source_val = c.get("source")
            if hasattr(source_val, "value"):
                source_str = source_val.value
            else:
                source_str = str(source_val or meta.get("source", "unknown"))

            formatted_chunks.append(
                {
                    "chunk_id": str(c.get("chunk_id") or c.get("id") or ""),
                    "source": source_str,
                    "document_id": str(
                        c.get("document_id")
                        or meta.get("document_id")
                        or meta.get("file_name")
                        or "doc"
                    ),
                    "content": str(c.get("content", "")),
                    "relevance_score": score,
                    "metadata": meta if isinstance(meta, dict) else {},
                }
            )

    chunk_scores = (
        [c["relevance_score"] for c in formatted_chunks]
        if formatted_chunks
        else [
            float(c.get("relevance_score", 0.0))
            for c in state.get("retrieved_chunks", [])
            if isinstance(c, dict)
        ]
    )

    resolved_trace_id = trace_id or state.get("trace_id") or str(uuid.uuid4())

    answer_val = state.get("final_answer")
    if not answer_val or not str(answer_val).strip():
        action_res = state.get("action_result")
        if isinstance(action_res, dict) and action_res.get("ticket_id"):
            t = action_res
            answer_val = (
                f"### Ticket Information: {t.get('ticket_id')}\n\n"
                f"- **Title:** {t.get('title')}\n"
                f"- **Status:** `{t.get('status', 'open')}`\n"
                f"- **Priority:** `{t.get('priority', 'N/A')}`\n"
                f"- **Category:** {t.get('category', 'General')}\n"
                f"- **Assignee:** {t.get('assignee', 'Unassigned')}\n"
                f"- **Description:** {t.get('description', 'No description.')}"
            )
            if t.get("resolution"):
                answer_val += f"\n- **Resolution:** {t.get('resolution')}"
        elif isinstance(action_res, dict) and action_res.get("message"):
            answer_val = str(action_res["message"])
        elif state.get("reasoning"):
            answer_val = str(state.get("reasoning"))
        else:
            answer_val = "Analysis completed. No further action needed."

    return QueryResponse(
        session_id=session_id,
        answer=str(answer_val),
        reasoning=state.get("reasoning", ""),
        action_taken=state.get("selected_action"),
        action_result=state.get("action_result"),
        sources=[c["source"] for c in formatted_chunks],
        retrieved_chunks=formatted_chunks,
        chunk_scores=chunk_scores,
        trace_id=resolved_trace_id,
    )

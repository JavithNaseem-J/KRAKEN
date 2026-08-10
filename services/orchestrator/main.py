from __future__ import annotations

import asyncio
import contextlib
import sys
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from langgraph.types import Command
try:
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    AsyncPostgresSaver = None  # type: ignore[assignment, misc]

try:
    from psycopg_pool import ConnectionPool
except ImportError:
    ConnectionPool = None  # type: ignore[assignment, misc]
from pydantic import BaseModel, Field

from shared.auth import verify_service_token
from shared.config import get_settings
from shared.http_client import create_async_http_client, service_headers
from shared.logging import configure_logging
from shared.models.agent import QueryRequest, QueryResponse

from .graph.agent_graph import build_graph_async
from .llm import validate_llm_config
from .observability import get_langfuse_callback_handler

log = structlog.get_logger(__name__)
settings = get_settings()


# ── Typed request schema for the callback endpoint ────────────────────────────
class ApprovalCallbackRequest(BaseModel):
    approval_id: str = Field(..., description="UUID issued by executor when HITL fired.")
    decision: Literal["approve", "reject"] = Field(
        ..., description="Human decision. Only 'approve' or 'reject' are valid."
    )


# ── Approval table DDL (idempotent) ───────────────────────────────────────────
_APPROVAL_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS approval_map (
    approval_id   TEXT        PRIMARY KEY,
    session_id    TEXT        NOT NULL,
    action_name   TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,
    resolved_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS approval_map_status_expires
    ON approval_map (status, expires_at)
    WHERE status = 'pending';
"""

# In-memory fallback for approval mappings when running without Postgres
_IN_MEMORY_APPROVAL_MAP: dict[str, dict[str, Any]] = {}


# ── Reaper background task ────────────────────────────────────────────────────
async def _reaper_loop(app: FastAPI) -> None:
    """
    Every 30 seconds, find pending approvals past their expiry, mark them as
    'timeout', and resume the graph with decision='timeout' so the thread
    cleans up and produces a final_answer.
    Also periodically prunes stale LangGraph checkpoints to prevent DB bloat.
    """
    loop_count = 0
    while True:
        await asyncio.sleep(30)
        loop_count += 1
        try:
            pool = getattr(app.state, "conn_pool", None)
            if pool is None:
                continue
            with pool.connection() as conn, conn.cursor() as cur:
                now = datetime.now(UTC)
                cur.execute(
                    """
                        UPDATE approval_map
                        SET    status = 'timeout', resolved_at = %s
                        WHERE  status = 'pending' AND expires_at < %s
                        RETURNING approval_id, session_id
                        """,
                    (now, now),
                )
                expired = cur.fetchall()

            for approval_id, session_id in expired:
                log.warning(
                    "reaper.timeout",
                    approval_id=approval_id,
                    session_id=session_id,
                )
                try:
                    config = _graph_config(session_id)
                    await app.state.agent_graph.ainvoke(
                        Command(resume={"decision": "timeout"}),
                        config,
                    )
                except Exception as exc:
                    log.error("reaper.resume_failed", session_id=session_id, error=str(exc))

            # ── Prune Stale Checkpoints (every ~30 minutes) ────────────────────
            if loop_count % 60 == 0:
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

            # 2. Prune checkpoints & writes for inactive sessions older than 7 days
            cur.execute(
                """
                WITH inactive AS (
                    SELECT session_id
                    FROM audit_log
                    WHERE timestamp < NOW() - INTERVAL '7 days'
                )
                DELETE FROM checkpoint_writes
                WHERE thread_id IN (SELECT session_id FROM inactive);
                """
            )
            deleted_counts["checkpoint_writes"] += cur.rowcount

            cur.execute(
                """
                WITH inactive AS (
                    SELECT session_id
                    FROM audit_log
                    WHERE timestamp < NOW() - INTERVAL '7 days'
                )
                DELETE FROM checkpoints
                WHERE thread_id IN (SELECT session_id FROM inactive);
                """
            )
            deleted_counts["checkpoints"] += cur.rowcount

            log.info("reaper.pruned_stale_checkpoints", **deleted_counts)
    except Exception as exc:
        log.error("reaper.prune_error", error=str(exc))

    return deleted_counts


# ── Lifespan ──────────────────────────────────────────────────────────────────
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
    if ConnectionPool and settings.postgres_sync_url:
        try:
            conn_pool = ConnectionPool(
                conninfo=settings.postgres_sync_url,
                min_size=1,
                max_size=10,
                max_idle=settings.postgres_max_idle_time,
                max_lifetime=1800.0,
                open=True,
                kwargs={
                    "autocommit": True,
                    "keepalives": settings.postgres_keepalives,
                    "keepalives_idle": settings.postgres_keepalives_idle,
                    "keepalives_interval": settings.postgres_keepalives_interval,
                    "keepalives_count": settings.postgres_keepalives_count,
                },
            )
            with conn_pool.connection() as conn:
                conn.execute(_APPROVAL_TABLE_DDL)
        except Exception as exc:
            log.warning("orchestrator.postgres_pool_failed", error=str(exc))
            conn_pool = None
    app.state.conn_pool = conn_pool

    # 4. Build the compiled graph (AsyncPostgresSaver with MemorySaver fallback)
    saver_cm = None
    if AsyncPostgresSaver and settings.postgres_sync_url:
        try:
            saver_cm = AsyncPostgresSaver.from_conn_string(settings.postgres_sync_url)
            saver = await saver_cm.__aenter__()
            app.state.saver_cm = saver_cm
            app.state.agent_graph = await build_graph_async(saver)
            log.info("orchestrator.async_checkpointer_ready")
        except Exception as exc:
            log.warning("orchestrator.async_checkpointer_failed", error=str(exc))
            saver_cm = None

    if saver_cm is None:
        app.state.saver_cm = None
        app.state.agent_graph = await build_graph_async(None)
        log.info("orchestrator.memory_checkpointer_ready")

    log.info("orchestrator.graph_ready")

    # 5. Start the reaper background task
    reaper_task = asyncio.create_task(_reaper_loop(app))
    log.info("orchestrator.reaper_started")

    # 6. Initialize concurrency semaphore
    semaphore = asyncio.Semaphore(settings.orchestrator_max_concurrency)
    from shared.cache import SemanticCache

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

    if getattr(app.state, "saver_cm", None):
        with contextlib.suppress(Exception):
            await app.state.saver_cm.__aexit__(None, None, None)

    if getattr(app.state, "conn_pool", None):
        with contextlib.suppress(Exception):
            app.state.conn_pool.close()
    log.info("orchestrator.shutdown")


# ── App ───────────────────────────────────────────────────────────────────────
from shared.middleware.trace_id import TraceIdMiddleware

app = FastAPI(
    title="KRAKEN Orchestrator",
    description="LangGraph Agent Orchestrator — Xiarch Cybersecurity Consultancy",
    version="0.5.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)

# ── Telemetry Setup ───────────────────────────────────────────────────────────
if _OTEL_AVAILABLE:
    try:
        _provider = TracerProvider()
        _processor = BatchSpanProcessor(ConsoleSpanExporter())
        _provider.add_span_processor(_processor)
        trace.set_tracer_provider(_provider)

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
    except Exception as exc:
        log.warning("orchestrator.telemetry_init_failed", error=str(exc))


def _graph_config(session_id: str) -> dict:
    """LangGraph thread config — all checkpointed state lives under this key."""
    cfg: dict[str, Any] = {"configurable": {"thread_id": session_id}}
    callbacks = get_langfuse_callback_handler()
    if callbacks:
        cfg["callbacks"] = callbacks
    return cfg


# ── Health ────────────────────────────────────────────────────────────────────
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
        if client is not None:
            resp = await client.get(url, headers=headers)
        else:
            async with create_async_http_client() as fallback_client:
                resp = await fallback_client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("messages", [])
    except Exception as exc:
        log.warning(
            "orchestrator.fetch_session_memory_failed", session_id=session_id, error=str(exc)
        )
    return []


# ── /run ──────────────────────────────────────────────────────────────────────
@app.post("/run", tags=["agent"])
async def run(body: QueryRequest) -> Any:
    """
    Execute the agent graph for a user query.
    Returns QueryResponse on completion, or pending_approval dict on HITL pause.
    """
    log.info("orchestrator.run", session_id=body.session_id, user_id=body.user_id)

    graph = app.state.agent_graph
    config = _graph_config(body.session_id)

    # ── Check if session is already completed or currently paused ─────────────
    snapshot = await graph.aget_state(config)
    if not body.message or body.message.strip().lower() in (
        "",
        "check status",
        "check approval status",
    ):
        if snapshot.values and "final_answer" in snapshot.values and not snapshot.next:
            log.info("orchestrator.status_check_completed", session_id=body.session_id)
            return _build_response(body.session_id, snapshot.values)
        if snapshot.next:
            interrupt_val: dict = {}
            for task in snapshot.tasks:
                for interrupt in getattr(task, "interrupts", []):
                    interrupt_val = interrupt.value
                    break
            approval_id = interrupt_val.get("approval_id")
            return {
                "status": "pending_approval",
                "approval_id": approval_id,
                "session_id": body.session_id,
                "message": "A CRITICAL triage action requires human approval. Check the approval service.",
            }

    http_client: httpx.AsyncClient | None = getattr(app.state, "http", None)

    # ── SemanticCache Lookup ──────────────────────────────────────────────────
    cache: SemanticCache | None = getattr(app.state, "semantic_cache", None)
    if cache and body.message and http_client:
        try:
            from shared.embedder import get_embedder
            embedder = get_embedder()
            query_vector = await asyncio.to_thread(embedder.embed_query, body.message)
            cached = await cache.get(query_vector)
            if cached:
                log.info("orchestrator.semantic_cache_hit", session_id=body.session_id)
                from services.action.audit_client import fire_audit_log
                asyncio.create_task(
                    fire_audit_log(
                        client=http_client,
                        session_id=body.session_id,
                        user_id=body.user_id,
                        action_type="READ",
                        action_name="cache_hit",
                        risk_level="SAFE",
                        hitl_required=False,
                        status="success",
                        reasoning="Returned answer directly from SemanticCache hit.",
                        payload={"query": body.message},
                        result={"answer": cached.get("response", cached.get("answer", ""))},
                    )
                )
                return QueryResponse(
                    session_id=body.session_id,
                    answer=cached.get("response", cached.get("answer", "")),
                    action_taken="auto_respond",
                    confidence=0.95,
                    reasoning="Answer retrieved from semantic response cache.",
                    evidence=["Semantic cache hit (similarity >= 0.92)"],
                    execution_time_sec=0.01,
                )
        except Exception as exc:
            log.warning("orchestrator.semantic_cache_lookup_failed", error=str(exc))

    session_messages = await _fetch_session_messages(body.session_id, client=http_client)

    initial_state = {
        "session_id": body.session_id,
        "user_id": body.user_id,
        "user_message": body.message,
        "messages": session_messages,
    }

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
        log.error("orchestrator.run_error", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if semaphore:
            semaphore.release()

    # ── Check if graph paused for HITL ────────────────────────────────────────
    snapshot = await graph.aget_state(config)
    if snapshot.next:
        interrupt_val: dict = {}
        for task in snapshot.tasks:
            for interrupt in getattr(task, "interrupts", []):
                interrupt_val = interrupt.value
                break

        approval_id = interrupt_val.get("approval_id", str(uuid.uuid4()))
        action_name = interrupt_val.get("action_name", "unknown")
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.approval_timeout_seconds)

        # Persist approval record to Postgres (durable) or in-memory fallback
        pool: ConnectionPool | None = getattr(app.state, "conn_pool", None)
        if pool is not None:
            try:
                with pool.connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO approval_map (approval_id, session_id, action_name, status, expires_at)
                        VALUES (%s, %s, %s, 'pending', %s)
                        ON CONFLICT (approval_id) DO NOTHING
                        """,
                        (approval_id, body.session_id, action_name, expires_at),
                    )
            except Exception as exc:
                log.warning("orchestrator.approval_db_save_failed", error=str(exc))
        else:
            _IN_MEMORY_APPROVAL_MAP[approval_id] = {
                "session_id": body.session_id,
                "action_name": action_name,
                "status": "pending",
                "expires_at": expires_at,
            }

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

    return _build_response(body.session_id, result)


# ── /approval-callback ────────────────────────────────────────────────────────
@app.post("/approval-callback", tags=["hitl"])
async def approval_callback(
    body: ApprovalCallbackRequest,
    _token: str = Depends(verify_service_token),
) -> Any:
    """
    Resume a paused graph after human approves or rejects a CRITICAL action.
    Called by the approval service with a valid X-Service-Token header.
    Idempotent: duplicate callbacks return 409 Conflict.
    """
    log.info(
        "orchestrator.callback_received",
        approval_id=body.approval_id,
        decision=body.decision,
    )

    pool: ConnectionPool | None = getattr(app.state, "conn_pool", None)

    # ── Phase 1: Idempotency check (read-only, no commit yet) ─────────────────
    session_id: str | None = None
    if pool is not None:
        try:
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                        SELECT session_id, status
                        FROM   approval_map
                        WHERE  approval_id = %s
                        FOR UPDATE
                        """,
                    (body.approval_id,),
                )
                row = cur.fetchone()

                if not row:
                    log.warning("orchestrator.callback_not_found", approval_id=body.approval_id)
                    raise HTTPException(status_code=404, detail="Approval ID not found.")

                session_id, current_status = row

                if current_status != "pending":
                    log.warning(
                        "orchestrator.callback_already_resolved",
                        approval_id=body.approval_id,
                        status=current_status,
                    )
                    raise HTTPException(
                        status_code=409,
                        detail=f"Approval already resolved with status '{current_status}'.",
                    )
        except HTTPException:
            raise
        except Exception as exc:
            log.warning("orchestrator.postgres_callback_check_failed", error=str(exc))
            pool = None

    if pool is None:
        rec = _IN_MEMORY_APPROVAL_MAP.get(body.approval_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Approval ID not found.")
        current_status = rec.get("status", "pending")
        if current_status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Approval already resolved with status '{current_status}'.",
            )
        session_id = rec.get("session_id")

    # ── Phase 2: Acquire bounded semaphore — same guard as /run ───────────────
    # A 503 here leaves the row 'pending' so the caller can retry the callback.
    semaphore: asyncio.Semaphore | None = getattr(app.state, "graph_semaphore", None)
    if semaphore:
        if semaphore.locked():
            log.warning(
                "orchestrator.callback_concurrency_limit_reached",
                approval_id=body.approval_id,
            )
            # Row stays 'pending' — caller can retry once capacity frees up.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server busy: maximum concurrent agent executions reached. Retry the callback.",
            )
        await semaphore.acquire()

    graph = app.state.agent_graph
    config = _graph_config(session_id or "")

    try:
        # ── Phase 3: Commit UPDATE then resume graph (semaphore held) ──────────
        if pool is not None:
            try:
                with pool.connection() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                            UPDATE approval_map
                            SET    status = %s, resolved_at = %s
                            WHERE  approval_id = %s AND status = 'pending'
                            """,
                        (body.decision, datetime.now(UTC), body.approval_id),
                    )
            except Exception as exc:
                log.warning("orchestrator.postgres_update_failed", error=str(exc))
        else:
            if body.approval_id in _IN_MEMORY_APPROVAL_MAP:
                _IN_MEMORY_APPROVAL_MAP[body.approval_id]["status"] = body.decision
        log.info(
            "orchestrator.resuming",
            session_id=session_id,
            approval_id=body.approval_id,
            decision=body.decision,
        )
        # Use ainvoke — nodes are now async; consistent with /run
        result = await graph.ainvoke(
            Command(resume={"decision": body.decision}),
            config,
        )
    except Exception as exc:
        log.error("orchestrator.resume_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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


# ── Helper ────────────────────────────────────────────────────────────────────
def _build_response(session_id: str, state: dict[str, Any]) -> QueryResponse:
    """Convert final graph state into a QueryResponse."""
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

            formatted_chunks.append({
                "chunk_id": str(c.get("chunk_id") or c.get("id") or ""),
                "source": source_str,
                "document_id": str(c.get("document_id") or meta.get("document_id") or meta.get("file_name") or "doc"),
                "content": str(c.get("content", "")),
                "relevance_score": score,
                "metadata": meta if isinstance(meta, dict) else {},
            })

    return QueryResponse(
        session_id=session_id,
        answer=state.get("final_answer", "No answer generated."),
        reasoning=state.get("reasoning", ""),
        action_taken=state.get("selected_action"),
        action_result=state.get("action_result"),
        sources=[c["source"] for c in formatted_chunks],
        retrieved_chunks=formatted_chunks,
    )

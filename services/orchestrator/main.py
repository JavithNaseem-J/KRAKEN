"""
Orchestrator Service — hosts the LangGraph agent and manages the request lifecycle.

Endpoints:
  GET  /health
  POST /run
      Starts a new agent run. Returns either:
        a) QueryResponse if the run completed (SAFE action / auto_respond)
        b) {"status": "pending_approval", "approval_id": "..."} if HITL fired

  POST /approval-callback
      Called by the approval service after a human decision.
      REQUIRES X-Service-Token header matching settings.hitl_service_token.
      Uses SELECT FOR UPDATE to guarantee idempotency — safe to retry.
      Returns the final QueryResponse.

Security:
  - /approval-callback is authenticated via a shared service token.
  - Approval state lives in Postgres (approval_map table), not in-memory.
  - Idempotency: duplicate callbacks return 409 Conflict.
  - Reaper: background task marks timed-out approvals and resumes the graph
    with decision="timeout" every 30 seconds.
  - Graph state is persisted via PostgresSaver — survives restarts.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, status
from langgraph.types import Command
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.models.agent import QueryRequest, QueryResponse

from .graph.agent_graph import build_graph
from .llm import validate_llm_config

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


# ── Reaper background task ────────────────────────────────────────────────────
async def _reaper_loop(app: FastAPI) -> None:
    """
    Every 30 seconds, find pending approvals past their expiry, mark them as
    'timeout', and resume the graph with decision='timeout' so the thread
    cleans up and produces a final_answer.
    """
    while True:
        await asyncio.sleep(30)
        try:
            pool: ConnectionPool = app.state.conn_pool
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
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda cfg=config: app.state.agent_graph.invoke(
                            Command(resume={"decision": "timeout"}),
                            cfg,
                        ),
                    )
                except Exception as exc:
                    log.error("reaper.resume_failed", session_id=session_id, error=str(exc))
        except Exception as exc:
            log.error("reaper.loop_error", error=str(exc))


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("orchestrator.startup", model=settings.llm_model)

    # 1. Fail fast on missing LLM key before we try to wire any graph
    validate_llm_config()

    # 2. Open a sync psycopg connection pool for PostgresSaver
    conn_pool = ConnectionPool(
        conninfo=settings.postgres_sync_url,
        min_size=1,
        max_size=10,
        open=True,
    )
    app.state.conn_pool = conn_pool

    # 3. Create approval_map table if it doesn't exist
    with conn_pool.connection() as conn:
        conn.execute(_APPROVAL_TABLE_DDL)

    # 4. Build the compiled graph (PostgresSaver uses conn_pool internally)
    app.state.agent_graph = build_graph(conn_pool)
    log.info("orchestrator.graph_ready")

    # 5. Start the reaper background task
    reaper_task = asyncio.create_task(_reaper_loop(app))
    log.info("orchestrator.reaper_started")

    yield

    # Shutdown
    reaper_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reaper_task

    # Clean up other nodes thread/connection pools
    from .graph.nodes.memory_writer import shutdown_thread_pool

    shutdown_thread_pool()

    conn_pool.close()
    log.info("orchestrator.shutdown")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AKEA Orchestrator",
    description="LangGraph Agent Orchestrator — Xiarch Cybersecurity Consultancy",
    version="0.5.0",
    lifespan=lifespan,
)

# ── Telemetry Setup ───────────────────────────────────────────────────────────
_provider = TracerProvider()
_processor = BatchSpanProcessor(ConsoleSpanExporter())
_provider.add_span_processor(_processor)
trace.set_tracer_provider(_provider)

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()


def _graph_config(session_id: str) -> dict:
    """LangGraph thread config — all checkpointed state lives under this key."""
    return {"configurable": {"thread_id": session_id}}


def _verify_service_token(
    x_service_token: str | None = Header(None, alias="X-Service-Token"),
) -> str:
    """
    FastAPI dependency: enforce shared-secret auth on the callback endpoint.
    Uses constant-time comparison to prevent timing attacks.
    """
    token = x_service_token or ""
    if not token or not secrets.compare_digest(token, settings.hitl_service_token):
        log.warning("orchestrator.callback_auth_failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing service token.",
        )
    return token


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    """Liveness probe. Checks connectivity to the Postgres saver pool."""
    db_ok = False
    try:
        pool: ConnectionPool = app.state.conn_pool
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

    initial_state = {
        "session_id": body.session_id,
        "user_id": body.user_id,
        "user_message": body.message,
        "messages": [],
    }

    try:
        # Run graph in separate worker thread to prevent blocking main event loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: graph.invoke(initial_state, config))
    except Exception as exc:
        log.error("orchestrator.run_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── Check if graph paused for HITL ────────────────────────────────────────
    snapshot = graph.get_state(config)
    if snapshot.next:
        interrupt_val: dict = {}
        for task in snapshot.tasks:
            for interrupt in getattr(task, "interrupts", []):
                interrupt_val = interrupt.value
                break

        approval_id = interrupt_val.get("approval_id", str(uuid.uuid4()))
        action_name = interrupt_val.get("action_name", "unknown")
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.approval_timeout_seconds)

        # Persist approval record to Postgres (durable, multi-replica safe)
        pool: ConnectionPool = app.state.conn_pool
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO approval_map (approval_id, session_id, action_name, status, expires_at)
                VALUES (%s, %s, %s, 'pending', %s)
                ON CONFLICT (approval_id) DO NOTHING
                """,
                (approval_id, body.session_id, action_name, expires_at),
            )

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
    _token: str = Depends(_verify_service_token),
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

    pool: ConnectionPool = app.state.conn_pool

    # ── Atomic idempotency: SELECT FOR UPDATE + UPDATE in one transaction ──────
    # Both operations share the same connection so the row lock is held
    # continuously. Two concurrent callbacks will serialize here — the second
    # one will see status != 'pending' and get a 409.
    session_id: str | None = None
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

        # ── Mark resolved inside the same transaction ──────────────────────
        cur.execute(
            """
                UPDATE approval_map
                SET    status = %s, resolved_at = %s
                WHERE  approval_id = %s AND status = 'pending'
                """,
            (body.decision, datetime.now(UTC), body.approval_id),
        )

    # ── Resume the graph ──────────────────────────────────────────────────────
    log.info(
        "orchestrator.resuming",
        session_id=session_id,
        approval_id=body.approval_id,
        decision=body.decision,
    )

    graph = app.state.agent_graph
    config = _graph_config(session_id)

    try:
        # Run graph resumption in separate worker thread to prevent blocking main event loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: graph.invoke(
                Command(resume={"decision": body.decision}),
                config,
            ),
        )
    except Exception as exc:
        log.error("orchestrator.resume_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _build_response(session_id, result)


# ── Helper ────────────────────────────────────────────────────────────────────
def _build_response(session_id: str, state: dict) -> QueryResponse:
    """Convert final graph state into a QueryResponse."""
    return QueryResponse(
        session_id=session_id,
        answer=state.get("final_answer", "No answer generated."),
        reasoning=state.get("reasoning", ""),
        action_taken=state.get("selected_action"),
        action_result=state.get("action_result"),
        sources=[
            c.get("metadata", {}).get("source", "unknown")
            for c in state.get("retrieved_chunks", [])[:3]
        ],
    )

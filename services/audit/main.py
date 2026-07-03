"""
Audit Service — full implementation with PostgreSQL persistence.

Called by the action service (fire-and-forget POST /log) after every action.
Also provides read-only history endpoints for operators.

Startup:
  - Creates asyncpg connection pool to PostgreSQL.
  - If PostgreSQL is unreachable, service degrades gracefully:
    logs are written to structlog only (not lost completely, captured by Docker).

Endpoints:
  GET  /health                     Liveness probe
  POST /log                        Write one audit entry (called by action service)
  GET  /history/{session_id}       Retrieve audit records for a session
  GET  /history/user/{user_id}     Retrieve recent audit records for a user
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.config import get_settings
from .audit_store import AuditStore
from .logger import configure_logging
from services.memory.db import create_pool   # Reuse the same pool factory

log      = structlog.get_logger(__name__)
settings = get_settings()


class AuditLogRequest(BaseModel):
    session_id:    str
    user_id:       str
    action_type:   str
    action_name:   str
    risk_level:    str
    hitl_required: bool
    status:        str
    reasoning:     str | None       = None
    payload:       dict | None      = None
    result:        dict | None      = None
    hitl_decision: str | None       = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
        service="audit",
    )

    log.info("audit.startup")

    try:
        pool = await create_pool(
            postgres_url=settings.postgres_url,
            min_size=2,
            max_size=8,   # Higher than memory: audit is write-heavy
        )
        app.state.store   = AuditStore(pool)
        app.state.db_pool = pool
        log.info("audit.db_ready")
    except Exception as exc:
        log.error("audit.db_unavailable", error=str(exc))
        app.state.store   = None
        app.state.db_pool = None

    yield

    if app.state.db_pool:
        await app.state.db_pool.close()
    log.info("audit.shutdown")


app = FastAPI(
    title="AKEA Audit",
    description="Append-Only Audit Log Service — Autonomous Knowledge Execution Agent",
    version="0.6.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    return {
        "status":  "ok",
        "service": "audit",
        "db":      app.state.store is not None,
    }


@app.post("/log", tags=["audit"])
async def log_action(body: AuditLogRequest) -> dict[str, Any]:
    """
    Write one audit entry. Always returns 200 — even on DB failure.
    Structlog captures the entry regardless, so logs are never truly lost.
    """
    # Always log to structlog first (captured by Docker log driver)
    log.info(
        "audit.entry",
        session_id=body.session_id,
        user_id=body.user_id,
        action=body.action_name,
        risk=body.risk_level,
        status=body.status,
        hitl_decision=body.hitl_decision,
    )

    if app.state.store is None:
        return {"status": "degraded", "message": "DB unavailable — logged to stdout only."}

    try:
        row_id = await app.state.store.log_action(**body.model_dump())
        return {"status": "ok", "id": row_id}
    except Exception as exc:
        log.error("audit.write_failed", error=str(exc))
        return {"status": "degraded", "message": str(exc)}


@app.get("/history/{session_id}", tags=["audit"])
async def session_history(session_id: str, limit: int = 50) -> dict[str, Any]:
    """Return audit records for a session (read-only, newest first)."""
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="Audit DB unavailable.")
    records = await app.state.store.get_session_history(session_id, limit=limit)
    return {"session_id": session_id, "records": records, "count": len(records)}


@app.get("/history/user/{user_id}", tags=["audit"])
async def user_history(user_id: str, limit: int = 100) -> dict[str, Any]:
    """Return recent audit records for a user across all sessions."""
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="Audit DB unavailable.")
    if app.state.db_pool is None:
        raise HTTPException(status_code=503, detail="Audit DB unavailable.")

    async with app.state.db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, timestamp, session_id, action_name, risk_level,
                   hitl_required, hitl_decision, status
            FROM   audit_log
            WHERE  user_id = $1
            ORDER  BY timestamp DESC
            LIMIT  $2
            """,
            user_id,
            min(limit, 200),
        )

    records = [dict(r) for r in rows]
    for r in records:
        if "timestamp" in r:
            r["timestamp"] = r["timestamp"].isoformat()
    return {"user_id": user_id, "records": records, "count": len(records)}

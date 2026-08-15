from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException

from shared.auth import verify_service_token
from shared.config import get_settings
from shared.db import create_pool, ensure_schema_async
from shared.logging import configure_logging
from shared.middleware.trace_id import TraceIdMiddleware
from shared.models.audit import AuditLogRequest

from .audit_store import AuditStore

log = structlog.get_logger(__name__)
settings = get_settings()


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
            max_size=8,  # Higher than memory: audit is write-heavy
        )
        await ensure_schema_async(pool)
        app.state.store = AuditStore(pool)
        app.state.db_pool = pool
        log.info("audit.db_ready")
    except Exception as exc:
        log.error("audit.db_unavailable", error=str(exc))
        app.state.store = None
        app.state.db_pool = None

    yield

    if app.state.db_pool:
        await app.state.db_pool.close()
    log.info("audit.shutdown")


app = FastAPI(
    title="KRAKEN Audit",
    description="Append-Only Audit Log Service — KRAKEN",
    version="0.6.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    db_ok = app.state.store is not None
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "audit",
        "db": db_ok,
    }


@app.post("/log", tags=["audit"])
async def log_action(
    body: AuditLogRequest,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
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
        row_id = await app.state.store.log_action(body)
        return {"status": "ok", "id": row_id}
    except Exception as exc:
        log.error("audit.write_failed", error=str(exc))
        return {"status": "degraded", "message": str(exc)}


@app.get("/history/{session_id}", tags=["audit"])
async def session_history(
    session_id: str,
    limit: int = 50,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Return audit records for a session (read-only, newest first). Requires service token."""
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="Audit DB unavailable.")
    capped_limit = min(limit, 200)
    records = await app.state.store.get_session_history(session_id, limit=capped_limit)
    return {"session_id": session_id, "records": records, "count": len(records)}


@app.get("/history/user/{user_id}", tags=["audit"])
async def user_history(
    user_id: str,
    limit: int = 100,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Return recent audit records for a user across all sessions. Requires service token."""
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="Audit DB unavailable.")
    capped_limit = min(limit, 200)
    records = await app.state.store.get_user_history(user_id, limit=capped_limit)
    return {"user_id": user_id, "records": records, "count": len(records)}


@app.get("/verify-chain", tags=["audit"])
async def verify_chain(
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Cryptographic SHA-256 hash chain verification endpoint. Detects DB tampering."""
    if app.state.store is None:
        raise HTTPException(status_code=503, detail="Audit DB unavailable.")
    return await app.state.store.verify_chain()

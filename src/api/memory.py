from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from src.utils.auth import verify_service_token
from src.utils.config import get_settings
from src.utils.logging import configure_logging
from src.utils.memory.short_term import ShortTermMemory
from src.utils.middleware.trace_id import TraceIdMiddleware

log = structlog.get_logger(__name__)
settings = get_settings()


# Request / Response models
class SessionUpdate(BaseModel):
    messages: list[dict[str, str]] = Field(..., max_length=100)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="memory"
    )
    # Short-term: Redis
    log.info("memory.startup.redis")
    short_term = ShortTermMemory(redis_url=settings.redis_url)

    # Fail-open: log warning if Redis is unreachable
    if not await short_term.ping():
        log.warning("memory.startup.redis_unreachable_running_degraded")

    app.state.short_term = short_term
    log.info("memory.startup.redis_ready")

    log.info("memory.startup.complete")
    yield

    await short_term.close()
    log.info("memory.shutdown")


app = FastAPI(
    title="KRAKEN Memory",
    description="Session Memory Service — KRAKEN",
    version="0.8.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)


# Ops
@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    """
    Report the availability of the retained Redis session store.
    """
    short_term = getattr(app.state, "short_term", None)
    short_term_ok = bool(short_term and await short_term.ping())
    return {
        "status": "ok" if short_term_ok else "degraded",
        "service": "memory",
        "short_term": short_term_ok,
    }


# Short-term memory
@app.get("/session/{session_id}", tags=["short-term"])
async def get_session(
    session_id: str,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Return conversation history for a session."""
    messages = await app.state.short_term.get_session(session_id)
    return {"session_id": session_id, "messages": messages, "turns": len(messages)}


@app.post("/session/{session_id}", tags=["short-term"])
async def update_session(
    session_id: str,
    body: SessionUpdate,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Replace the entire session message history."""
    await app.state.short_term.update_session(session_id, body.messages)
    return {"session_id": session_id, "turns": len(body.messages), "status": "updated"}


@app.post("/session/{session_id}/append", tags=["short-term"])
async def append_to_session(
    session_id: str,
    body: SessionUpdate,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Atomically append messages to existing session history."""
    updated = await app.state.short_term.append_messages(session_id, body.messages)
    return {"session_id": session_id, "turns": len(updated), "status": "appended"}


@app.delete("/session/{session_id}", tags=["short-term"])
async def clear_session(
    session_id: str,
    _token: str = Depends(verify_service_token),
) -> dict[str, str]:
    """Delete session from Redis."""
    await app.state.short_term.clear_session(session_id)
    return {"session_id": session_id, "status": "cleared"}

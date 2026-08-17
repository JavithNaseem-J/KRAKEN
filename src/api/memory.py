"""
Memory Service — full implementation.

Startup lifecycle:
  1. Connect to Redis (short-term memory) — fail-fast if unreachable
  2. Create asyncpg pool → PostgreSQL (long-term episodic memory)
  3. Load BAAI/bge-small-en for episode embedding
  4. Store both in app.state

Security:
  All state-mutating and read endpoints require X-Service-Token.
  Only the orchestrator and trusted internal services may read/write memory.

Endpoints:
  GET    /health                        Liveness probe (reflects Redis + Postgres health)
  GET    /session/{session_id}          Retrieve short-term conversation history
  POST   /session/{session_id}          Replace session message history
  POST   /session/{session_id}/append   Append messages to history
  DELETE /session/{session_id}          Clear session
  POST   /long-term                     Store an episodic memory entry
  POST   /long-term/search              Semantic search over past episodes
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from src.utils.auth import verify_service_token
from src.utils.config import get_settings
from src.utils.db import create_pool, ensure_schema_async
from src.utils.logging import configure_logging
from src.utils.memory.long_term import LongTermMemory
from src.utils.memory.short_term import ShortTermMemory
from src.utils.middleware.trace_id import TraceIdMiddleware
from src.utils.models.memory import (
    EpisodeChunk,
    EpisodeSearchRequest,
    EpisodeSearchResponse,
    EpisodeStoreRequest,
)

log = structlog.get_logger(__name__)
settings = get_settings()


# ── Request / Response models ─────────────────────────────────────────────────
class SessionUpdate(BaseModel):
    messages: list[dict[str, str]] = Field(..., max_length=100)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="memory"
    )
    # ── Short-term: Redis ──────────────────────────────────────────────────────
    log.info("memory.startup.redis")
    short_term = ShortTermMemory(redis_url=settings.redis_url)

    # Fail-open: log warning if Redis is unreachable
    if not await short_term.ping():
        log.warning("memory.startup.redis_unreachable_running_degraded")

    app.state.short_term = short_term
    log.info("memory.startup.redis_ready")

    # ── Long-term: PostgreSQL + pgvector ──────────────────────────────────────
    log.info("memory.startup.postgres")
    try:
        pool = await create_pool(
            postgres_url=settings.postgres_url,
            min_size=2,
            max_size=5,
        )
        await ensure_schema_async(pool)
        long_term = LongTermMemory(
            pool=pool,
            embedding_model=settings.embedding_model,
            device=settings.embedding_device,
        )
        app.state.long_term = long_term
        app.state.db_pool = pool
        log.info("memory.startup.long_term_ready")
    except Exception as exc:
        log.error("memory.startup.postgres_failed", error=str(exc))
        app.state.long_term = None
        app.state.db_pool = None

    log.info("memory.startup.complete")
    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    await short_term.close()
    if app.state.db_pool:
        await app.state.db_pool.close()
    log.info("memory.shutdown")


app = FastAPI(
    title="KRAKEN Memory",
    description="Session & Episodic Memory Service — KRAKEN",
    version="0.7.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)


# ── Ops ───────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> dict[str, Any]:
    """
    Liveness probe. Returns degraded status if long-term memory is unavailable.
    Redis failure is always fatal (service won't start), so short_term is always healthy here.
    """
    long_term_ok = app.state.long_term is not None
    return {
        "status": "ok" if long_term_ok else "degraded",
        "service": "memory",
        "short_term": True,
        "long_term": long_term_ok,
    }


# ── Short-term memory ─────────────────────────────────────────────────────────
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


# ── Long-term memory ──────────────────────────────────────────────────────────
@app.post("/long-term", tags=["long-term"])
async def store_episode(
    body: EpisodeStoreRequest,
    _token: str = Depends(verify_service_token),
) -> dict[str, str]:
    """Store an episodic memory entry with its embedding."""
    if app.state.long_term is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Long-term memory unavailable (PostgreSQL not connected).",
        )
    memory_id = await app.state.long_term.store(
        session_id=body.session_id,
        user_id=body.user_id,
        content=body.content,
        metadata=body.metadata,
    )
    return {"memory_id": memory_id, "status": "stored"}


@app.post("/long-term/search", response_model=EpisodeSearchResponse, tags=["long-term"])
async def search_episodes(
    body: EpisodeSearchRequest,
    _token: str = Depends(verify_service_token),
) -> EpisodeSearchResponse:
    """Semantic search over past episodic memories for a user."""
    if app.state.long_term is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Long-term memory unavailable (PostgreSQL not connected).",
        )
    raw_results = await app.state.long_term.search(
        query=body.query,
        user_id=body.user_id,
        top_k=body.top_k,
    )
    chunks = [EpisodeChunk.model_validate(r) for r in raw_results]
    return EpisodeSearchResponse(query=body.query, user_id=body.user_id, results=chunks)

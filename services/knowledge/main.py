"""
Knowledge Service — Qdrant Vector Search Implementation.

Startup lifecycle:
  1. Load BAAI/bge-small-en embedding model
  2. Open QdrantClient (remote Cloud or local in-memory fallback)
  3. Ensure `akea_knowledge` collection exists
  4. Instantiate KnowledgeRetriever and store in app.state

Endpoints:
  GET  /health     — liveness probe
  POST /retrieve   — multi-source semantic search (authenticated)
  POST /ingest     — trigger re-ingestion (admin, authenticated)
  GET  /stats      — collection point count
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException

from shared.auth import verify_service_token
from shared.config import get_settings
from shared.logging import configure_logging
from shared.models.knowledge import RetrievalRequest, RetrievalResult

from shared.embedder import BGEEmbedder
from .retriever import KnowledgeRetriever

log = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="knowledge"
    )
    from shared.embedder import get_embedder

    # ── 1. Load embedding model ────────────────────────────────────────────────
    log.info("knowledge.startup.embedder", model=settings.embedding_model)
    embedder = get_embedder()

    # ── 2. Open Qdrant client & ensure collection ──────────────────────────────
    try:
        from shared.cache import create_async_qdrant_client
        client = create_async_qdrant_client()

        from .ingest import ensure_collection
        await ensure_collection(client, settings.qdrant_collection_name, vector_size=384)

        app.state.client = client
        app.state.embedder = embedder
        app.state.retriever = KnowledgeRetriever(
            client=client, embedder=embedder, collection_name=settings.qdrant_collection_name
        )

        info = await client.get_collection(settings.qdrant_collection_name)
        if (info.points_count or 0) == 0:
            log.info("knowledge.startup.auto_ingest_starting")
            from .ingest import run_ingest_async
            counts = await run_ingest_async(client, embedder)
            log.info("knowledge.startup.auto_ingest_complete", counts=counts)
    except Exception as exc:
        log.warning("knowledge.startup.qdrant_degraded", error=str(exc))
        app.state.client = None
        app.state.embedder = embedder
        app.state.retriever = None

    log.info("knowledge.startup.complete")
    yield

    log.info("knowledge.shutdown")


from shared.middleware.trace_id import TraceIdMiddleware

app = FastAPI(
    title="KRAKEN Knowledge",
    description="Multi-source Knowledge Retrieval — KRAKEN",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "knowledge"}


@app.get("/stats", tags=["ops"])
async def stats() -> dict[str, int]:
    """Return total document point count in Qdrant collection."""
    try:
        info = await app.state.client.get_collection(settings.qdrant_collection_name)
        count = info.points_count or 0
    except Exception as exc:
        log.warning("knowledge.stats_error", error=str(exc))
        count = 0
    return {settings.qdrant_collection_name: count}


@app.post("/retrieve", response_model=RetrievalResult, tags=["retrieval"])
async def retrieve(
    body: RetrievalRequest,
    _token: str = Depends(verify_service_token),
) -> RetrievalResult:
    """Semantic search across all requested knowledge sources."""
    try:
        return await app.state.retriever.retrieve(body)
    except Exception as exc:
        log.error("knowledge.retrieve_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {exc}") from exc


@app.post("/ingest", tags=["admin"])
async def ingest(
    _token: str = Depends(verify_service_token),
) -> dict[str, int]:
    """
    Trigger re-ingestion of all knowledge sources from disk into Qdrant.
    Called by the ingest script or admin endpoint via HTTP.
    """
    try:
        from .ingest import run_ingest_async  # noqa: PLC0415

        counts = await run_ingest_async(app.state.client, app.state.embedder)
        log.info("knowledge.ingest.complete", counts=counts)
        return counts
    except Exception as exc:
        log.error("knowledge.ingest_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

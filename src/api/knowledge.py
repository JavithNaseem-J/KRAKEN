from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from src.utils.auth import verify_service_token
from src.utils.config import get_settings
from src.utils.http_client import simple_health_response
from src.utils.knowledge.retriever import KnowledgeRetriever
from src.utils.logging import configure_logging
from src.utils.middleware.trace_id import TraceIdMiddleware
from src.utils.models.knowledge import RetrievalRequest, RetrievalResult

log = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(
        log_level=settings.log_level, log_format=settings.log_format, service="knowledge"
    )
    embedder: Any
    if settings.qdrant_url and settings.qdrant_cloud_inference_enabled:
        embedder = None
        log.info("knowledge.startup.qdrant_cloud_inference", model=settings.qdrant_inference_model)
    else:
        from src.utils.embedder import get_embedder

        log.info("knowledge.startup.embedder", model=settings.embedding_model)
        embedder = get_embedder()

    # 2. Open Qdrant client & ensure collection
    try:
        from src.utils.cache import create_async_qdrant_client

        client = create_async_qdrant_client()

        from src.utils.knowledge.ingest import ensure_collection

        await ensure_collection(client, settings.qdrant_collection_name)

        app.state.client = client
        app.state.embedder = embedder
        app.state.retriever = KnowledgeRetriever(
            client=client, embedder=embedder, collection_name=settings.qdrant_collection_name
        )

        info = await client.get_collection(settings.qdrant_collection_name)
        if (info.points_count or 0) == 0:
            log.info("knowledge.startup.auto_ingest_starting")
            from src.utils.knowledge.ingest import run_ingest_async

            counts = await run_ingest_async(client, embedder)
            log.info("knowledge.startup.auto_ingest_complete", counts=counts)
    except Exception as exc:
        log.warning("knowledge.startup.qdrant_degraded", error=exc.__class__.__name__)
        app.state.client = None
        app.state.embedder = embedder
        app.state.retriever = None

    log.info("knowledge.startup.complete")
    yield

    log.info("knowledge.shutdown")


app = FastAPI(
    title="KRAKEN Knowledge",
    description="Multi-source Knowledge Retrieval — KRAKEN",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(TraceIdMiddleware)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return simple_health_response("knowledge")


@app.get("/stats", tags=["ops"])
async def stats() -> dict[str, int]:
    """Return total document point count in Qdrant collection."""
    try:
        info = await app.state.client.get_collection(settings.qdrant_collection_name)
        count = info.points_count or 0
    except Exception as exc:
        log.warning("knowledge.stats_error", error=exc.__class__.__name__)
        count = 0
    return {settings.qdrant_collection_name: count}


@app.post("/retrieve", response_model=RetrievalResult, tags=["retrieval"])
async def retrieve(
    body: RetrievalRequest,
    _token: str = Depends(verify_service_token),
) -> RetrievalResult:
    """Semantic search across all requested knowledge sources."""
    try:
        retriever = getattr(app.state, "retriever", None)
        if not retriever:
            from src.utils.cache import create_async_qdrant_client
            from src.utils.embedder import get_embedder

            embedder = get_embedder()
            client = getattr(app.state, "client", None) or create_async_qdrant_client()
            retriever = KnowledgeRetriever(
                client=client, embedder=embedder, collection_name=settings.qdrant_collection_name
            )
            app.state.retriever = retriever
        return await retriever.retrieve(body)
    except Exception as exc:
        log.error("knowledge.retrieve_error", error=exc.__class__.__name__)
        return RetrievalResult(
            query=body.query, chunks=[], total_retrieved=0, sources_queried=body.sources
        )


@app.post("/ingest", tags=["admin"])
async def ingest(
    _token: str = Depends(verify_service_token),
) -> dict[str, int]:
    """
    Trigger re-ingestion of all knowledge sources from disk into Qdrant.
    Called by the ingest script or admin endpoint via HTTP.
    """
    try:
        from src.utils.cache import SemanticCache  # noqa: PLC0415
        from src.utils.knowledge.ingest import run_ingest_async  # noqa: PLC0415

        counts = await run_ingest_async(app.state.client, app.state.embedder)
        try:
            cache = SemanticCache(client=app.state.client)
            await cache.invalidate()
        except Exception as exc:
            log.warning("knowledge.cache_invalidation_error", error=exc.__class__.__name__)

        log.info("knowledge.ingest.complete", counts=counts)
        return counts
    except Exception as exc:
        log.error("knowledge.ingest_failed", error=exc.__class__.__name__)
        raise HTTPException(status_code=500, detail="Knowledge ingestion failed.") from exc


@app.post("/upload", tags=["admin"])
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    allowed_roles: Annotated[str, Form()] = "public",
    public_session_id: Annotated[str | None, Form()] = None,
    expires_at: Annotated[float | None, Form()] = None,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Dynamically parse, embed, and ingest an uploaded document file into Qdrant."""
    try:
        from src.utils.knowledge.ingest import (
            cleanup_expired_private_points,
            ingest_uploaded_file_async,
        )

        content_bytes = await file.read()
        await cleanup_expired_private_points(app.state.client)
        roles_list = [r.strip().lower() for r in allowed_roles.split(",") if r.strip()] or [
            "public"
        ]
        count = await ingest_uploaded_file_async(
            client=app.state.client,
            embedder=app.state.embedder,
            filename=file.filename or "uploaded_doc.txt",
            file_bytes=content_bytes,
            allowed_roles=roles_list,
            public_session_id=public_session_id,
            expires_at=expires_at,
        )
        from src.utils.cache import SemanticCache

        await SemanticCache(client=app.state.client).invalidate()
        return {
            "status": "success",
            "filename": file.filename,
            "chunks_ingested": count,
            "allowed_roles": roles_list,
        }
    except Exception as exc:
        log.error("knowledge.upload_failed", error=exc.__class__.__name__)
        raise HTTPException(status_code=500, detail="Upload processing failed.") from exc

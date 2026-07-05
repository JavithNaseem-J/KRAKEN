"""
Knowledge Service — full implementation.

Startup lifecycle:
  1. Load BAAI/bge-small-en embedding model (downloads once, cached by HuggingFace)
  2. Open ChromaDB persistent client
  3. Get-or-create collections for all three knowledge sources
  4. Instantiate KnowledgeRetriever and store in app.state

Endpoints:
  GET  /health     — liveness probe
  POST /retrieve   — multi-source semantic search (authenticated)
  POST /ingest     — trigger re-ingestion (admin, called by ingest script, authenticated)
  GET  /stats      — collection document counts per source
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import chromadb
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, status

from shared.config import get_settings
from shared.models.knowledge import KnowledgeSource, RetrievalRequest, RetrievalResult

from .embedder import BGEEmbedder
from .retriever import KnowledgeRetriever, _source_to_collection_name

log = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── 1. Load embedding model ────────────────────────────────────────────────
    log.info("knowledge.startup.embedder", model=settings.embedding_model)
    embedder = BGEEmbedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )

    # ── 2. Open ChromaDB persistent client ────────────────────────────────────
    log.info("knowledge.startup.chroma", path=settings.chroma_persist_dir)
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

    # ── 3. Get or create one collection per knowledge source ──────────────────
    collections: dict[str, chromadb.Collection] = {}
    for source in KnowledgeSource:
        name = _source_to_collection_name(source)
        col = client.get_or_create_collection(
            name=name,
            embedding_function=embedder,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )
        collections[name] = col
        log.info("knowledge.collection_ready", name=name, count=col.count())

    # Create semantic query cache collection
    query_cache_col = client.get_or_create_collection(
        name="akea_query_cache",
        embedding_function=embedder,  # type: ignore[arg-type]
        metadata={"hnsw:space": "cosine"},
    )
    collections["query_cache"] = query_cache_col
    log.info("knowledge.query_cache_ready", count=query_cache_col.count())

    # ── 4. Store retriever in app state ───────────────────────────────────────
    app.state.retriever = KnowledgeRetriever(client=client, collections=collections)
    app.state.collections = collections
    app.state.embedder = embedder

    log.info("knowledge.startup.complete")
    yield

    log.info("knowledge.shutdown")


app = FastAPI(
    title="AKEA Knowledge",
    description="Multi-source Knowledge Retrieval — Autonomous Knowledge Execution Agent",
    version="0.2.0",
    lifespan=lifespan,
)


def _verify_service_token(
    x_service_token: str | None = Header(None, alias="X-Service-Token"),
) -> str:
    """FastAPI dependency: Enforce service token validation."""
    token = x_service_token or ""
    if not token or not secrets.compare_digest(token, settings.hitl_service_token):
        log.warning("knowledge.auth_failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing service token.",
        )
    return token


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "knowledge"}


@app.get("/stats", tags=["ops"])
async def stats() -> dict[str, int]:
    """Return document count per collection."""
    return {name: col.count() for name, col in app.state.collections.items()}


@app.post("/retrieve", response_model=RetrievalResult, tags=["retrieval"])
async def retrieve(
    body: RetrievalRequest,
    _token: str = Depends(_verify_service_token),
) -> RetrievalResult:
    """Semantic search across all requested knowledge sources."""
    try:
        return await app.state.retriever.retrieve(body)
    except Exception as exc:
        log.error("knowledge.retrieve_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {exc}") from exc


def _run_ingest(collections: dict[str, Any]) -> dict[str, int]:
    """Helper executed in worker thread to perform file loading and collection upsert."""
    from .loaders.faq_loader import load_faq_chunks
    from .loaders.sla_loader import load_sla_chunks
    from .loaders.ticket_loader import load_ticket_chunks

    counts: dict[str, int] = {}

    # FAQ
    faq_chunks = load_faq_chunks()
    if faq_chunks:
        col = collections[_source_to_collection_name(KnowledgeSource.FAQ)]
        col.upsert(
            ids=[c["id"] for c in faq_chunks],
            documents=[c["document"] for c in faq_chunks],
            metadatas=[c["metadata"] for c in faq_chunks],
        )
    counts["faq"] = len(faq_chunks)

    # Tickets
    ticket_chunks, _ = load_ticket_chunks()
    if ticket_chunks:
        col = collections[_source_to_collection_name(KnowledgeSource.TICKETS)]
        col.upsert(
            ids=[c["id"] for c in ticket_chunks],
            documents=[c["document"] for c in ticket_chunks],
            metadatas=[c["metadata"] for c in ticket_chunks],
        )
    counts["tickets"] = len(ticket_chunks)

    # SLA
    sla_chunks = load_sla_chunks()
    if sla_chunks:
        col = collections[_source_to_collection_name(KnowledgeSource.SLA)]
        col.upsert(
            ids=[c["id"] for c in sla_chunks],
            documents=[c["document"] for c in sla_chunks],
            metadatas=[c["metadata"] for c in sla_chunks],
        )
    counts["sla"] = len(sla_chunks)

    return counts


@app.post("/ingest", tags=["admin"])
async def ingest(
    _token: str = Depends(_verify_service_token),
) -> dict[str, int]:
    """
    Trigger re-ingestion of all knowledge sources from disk.
    Called by the ingest script via HTTP. Idempotent — uses upsert.
    """
    loop = asyncio.get_running_loop()
    try:
        counts = await loop.run_in_executor(None, _run_ingest, app.state.collections)
        log.info("knowledge.ingest.complete", counts=counts)
        return counts
    except Exception as exc:
        log.error("knowledge.ingest_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

"""
Knowledge Service — full implementation.

Startup lifecycle:
  1. Load BAAI/bge-small-en embedding model (downloads once, cached by HuggingFace)
  2. Open ChromaDB persistent client
  3. Get-or-create collections for all three knowledge sources
  4. Instantiate KnowledgeRetriever and store in app.state

Endpoints:
  GET  /health     — liveness probe
  POST /retrieve   — multi-source semantic search
  POST /ingest     — trigger re-ingestion (admin, called by ingest script)
  GET  /stats      — collection document counts per source
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import chromadb
import structlog
from fastapi import FastAPI, HTTPException

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
            embedding_function=embedder,     # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )
        collections[name] = col
        log.info("knowledge.collection_ready", name=name, count=col.count())

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


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "knowledge"}


@app.get("/stats", tags=["ops"])
async def stats() -> dict[str, int]:
    """Return document count per collection."""
    return {
        name: col.count()
        for name, col in app.state.collections.items()
    }


@app.post("/retrieve", response_model=RetrievalResult, tags=["retrieval"])
async def retrieve(body: RetrievalRequest) -> RetrievalResult:
    """Semantic search across all requested knowledge sources."""
    try:
        return await app.state.retriever.retrieve(body)
    except Exception as exc:
        log.error("knowledge.retrieve_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {exc}") from exc


@app.post("/ingest", tags=["admin"])
async def ingest() -> dict[str, int]:
    """
    Trigger re-ingestion of all knowledge sources from disk.
    Called by the ingest script via HTTP. Idempotent — uses upsert.
    """
    from .loaders.faq_loader    import load_faq_chunks
    from .loaders.ticket_loader import load_ticket_chunks
    from .loaders.sla_loader    import load_sla_chunks

    counts: dict[str, int] = {}

    # FAQ
    faq_chunks = load_faq_chunks()
    if faq_chunks:
        col = app.state.collections[_source_to_collection_name(KnowledgeSource.FAQ)]
        col.upsert(
            ids=[c["id"] for c in faq_chunks],
            documents=[c["document"] for c in faq_chunks],
            metadatas=[c["metadata"] for c in faq_chunks],
        )
    counts["faq"] = len(faq_chunks)

    # Tickets
    ticket_chunks, _ = load_ticket_chunks()
    if ticket_chunks:
        col = app.state.collections[_source_to_collection_name(KnowledgeSource.TICKETS)]
        col.upsert(
            ids=[c["id"] for c in ticket_chunks],
            documents=[c["document"] for c in ticket_chunks],
            metadatas=[c["metadata"] for c in ticket_chunks],
        )
    counts["tickets"] = len(ticket_chunks)

    # SLA
    sla_chunks = load_sla_chunks()
    if sla_chunks:
        col = app.state.collections[_source_to_collection_name(KnowledgeSource.SLA)]
        col.upsert(
            ids=[c["id"] for c in sla_chunks],
            documents=[c["document"] for c in sla_chunks],
            metadatas=[c["metadata"] for c in sla_chunks],
        )
    counts["sla"] = len(sla_chunks)

    log.info("knowledge.ingest.complete", counts=counts)
    return counts

"""
Knowledge ingestion pipeline — runs all three loaders and upserts into ChromaDB.

Usage:
    make ingest
    python scripts/ingest_knowledge.py

Can also be triggered via HTTP after the knowledge service is running:
    curl -X POST http://localhost:8002/ingest

This script runs the loaders directly (not via HTTP) so it can be used
before the service is started — e.g., pre-seeding before `make up`.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
import structlog

from shared.config import get_settings
from shared.models.knowledge import KnowledgeSource
from services.knowledge.embedder import BGEEmbedder
from services.knowledge.loaders.faq_loader import load_faq_chunks
from services.knowledge.loaders.ticket_loader import load_ticket_chunks
from services.knowledge.loaders.sla_loader import load_sla_chunks
from services.knowledge.retriever import _source_to_collection_name

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
log = structlog.get_logger()
settings = get_settings()


def _upsert(
    collection: chromadb.Collection,
    chunks: list[dict],
    label: str,
) -> int:
    if not chunks:
        log.warning("ingest.empty_source", source=label)
        return 0
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["document"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    log.info("ingest.upserted", source=label, count=len(chunks))
    return len(chunks)


def main() -> None:
    print()
    print("=" * 56)
    print("  AKEA Knowledge Ingestion Pipeline")
    print("=" * 56)
    print(f"  Chroma dir     : {settings.chroma_persist_dir}")
    print(f"  Embedding model: {settings.embedding_model}")
    print()

    t0 = time.perf_counter()

    # ── Load embedding model ───────────────────────────────────────────────────
    log.info("ingest.loading_embedder", model=settings.embedding_model)
    embedder = BGEEmbedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )

    # ── Open ChromaDB ──────────────────────────────────────────────────────────
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

    totals: dict[str, int] = {}

    for source in KnowledgeSource:
        col = client.get_or_create_collection(
            name=_source_to_collection_name(source),
            embedding_function=embedder,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )

        if source == KnowledgeSource.FAQ:
            chunks = load_faq_chunks()
            totals["faq"] = _upsert(col, chunks, "faq")

        elif source == KnowledgeSource.TICKETS:
            chunks, _ = load_ticket_chunks()
            totals["tickets"] = _upsert(col, chunks, "tickets")

        elif source == KnowledgeSource.SLA:
            chunks = load_sla_chunks()
            totals["sla"] = _upsert(col, chunks, "sla")

    elapsed = time.perf_counter() - t0

    print()
    print("=" * 56)
    print("  Ingestion complete")
    print(f"  FAQ chunks     : {totals.get('faq', 0)}")
    print(f"  Ticket chunks  : {totals.get('tickets', 0)}")
    print(f"  SLA chunks     : {totals.get('sla', 0)}")
    print(f"  Total          : {sum(totals.values())}")
    print(f"  Elapsed        : {elapsed:.2f}s")
    print("=" * 56)
    print()


if __name__ == "__main__":
    main()

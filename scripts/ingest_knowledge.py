from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from src.utils.cache import create_async_qdrant_client
from src.utils.config import get_settings
from src.utils.embedder import BGEEmbedder
from src.utils.knowledge.ingest import run_ingest_async

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
log = structlog.get_logger()
settings = get_settings()


async def main_async() -> None:
    print()
    print("=" * 56)
    print("  AKEA Knowledge Ingestion Pipeline (Qdrant)")
    print("=" * 56)
    print(f"  Qdrant URL     : {settings.qdrant_url or ':memory:'}")
    print(f"  Collection     : {settings.qdrant_collection_name}")
    print(f"  Embedding model: {settings.embedding_model}")
    print()

    t0 = time.perf_counter()

    log.info("ingest.loading_embedder", model=settings.embedding_model)
    embedder = BGEEmbedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )

    client = create_async_qdrant_client()

    try:
        totals = await run_ingest_async(client, embedder)
    finally:
        await client.close()

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


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

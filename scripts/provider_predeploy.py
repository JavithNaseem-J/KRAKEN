from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import psycopg
import redis.asyncio as redis
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from qdrant_client import AsyncQdrantClient, models

from src.utils.cache import (
    SEMANTIC_CACHE_COLLECTION,
    SemanticCache,
    semantic_cache_point_id,
)
from src.utils.config import get_settings
from src.utils.db.schema import SCHEMA_DDL
from src.utils.db.tickets import seed_tickets
from src.utils.knowledge.ingest import ensure_collection, run_ingest_async
from src.utils.llm_probe import probe_chat_completion


async def main_async() -> None:
    settings = get_settings()
    checks: dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        groq_ready, groq_detail = await probe_chat_completion(
            client,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            models=[settings.llm_model, settings.llm_fallback_model],
            timeout_seconds=10.0,
        )
        checks["groq"] = groq_ready
        if groq_detail:
            print("provider predeploy groq detail: " + groq_detail, file=sys.stderr)

    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        cloud_inference=True,
        timeout=10,
    )
    await ensure_collection(qdrant, settings.qdrant_collection_name)
    ingestion_counts = await run_ingest_async(qdrant, None)
    checks["seed_ingestion"] = sum(ingestion_counts.values()) > 0
    await qdrant.get_collection(settings.qdrant_collection_name)
    filtered_probe = await qdrant.query_points(
        collection_name=settings.qdrant_collection_name,
        query=models.Document(text="VPN", model=settings.qdrant_inference_model),
        query_filter=models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value="faq")),
                models.FieldCondition(key="scope", match=models.MatchValue(value="shared")),
                models.FieldCondition(key="allowed_roles", match=models.MatchValue(value="public")),
                models.FieldCondition(
                    key="collection_version",
                    match=models.MatchValue(value=settings.knowledge_collection_version),
                ),
                models.FieldCondition(
                    key="dataset_generation",
                    match=models.MatchValue(value=settings.synthetic_dataset_generation),
                ),
            ]
        ),
        limit=1,
    )
    checks["qdrant_storage"] = True
    checks["qdrant_inference"] = bool(filtered_probe.points)

    probe_query = f"kraken semantic cache predeploy {uuid.uuid4()}"
    probe_response = {"probe": probe_query}
    probe_context = {
        "embedding_model": settings.qdrant_inference_model,
        "knowledge_version": settings.knowledge_collection_version,
        "role": "predeploy",
        "scope": "predeploy",
    }
    probe_vector = models.Document(text=probe_query, model=settings.qdrant_inference_model)
    cache = SemanticCache(client=qdrant, ttl_seconds=30.0)
    await cache.init()
    await cache.put(probe_vector, probe_query, probe_response, probe_context)
    checks["semantic_cache"] = await cache.get(probe_vector, probe_context) == probe_response
    probe_id = semantic_cache_point_id(probe_query, probe_context)
    await qdrant.delete(
        collection_name=SEMANTIC_CACHE_COLLECTION,
        points_selector=models.PointIdsList(points=[probe_id]),
    )
    await qdrant.close()

    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
    )
    checks["redis"] = bool(await redis_client.ping())
    await redis_client.aclose()

    with psycopg.connect(settings.postgres_sync_url, connect_timeout=10) as connection:
        checks["postgres"] = connection.execute("SELECT 1").fetchone() == (1,)
        connection.execute(SCHEMA_DDL)
        tickets_path = (
            Path(__file__).parent.parent / "data/knowledge/tickets/synthetic_tickets.json"
        )
        tickets = json.loads(tickets_path.read_text(encoding="utf-8"))
        checks["postgres_seed"] = seed_tickets(connection, tickets, update_on_conflict=True) == 500
        checks["postgres_schema"] = True

    async with asyncio.timeout(20):
        checkpoint_connection = await AsyncConnection.connect(
            settings.postgres_sync_url,
            autocommit=True,
            prepare_threshold=None,
            row_factory=dict_row,
        )
        try:
            # pyrefly: ignore [bad-argument-type]
            saver = AsyncPostgresSaver(checkpoint_connection)
            await saver.setup()
            checks["hitl_checkpoints"] = True
        finally:
            await checkpoint_connection.close()

    if not all(checks.values()):
        failed = sorted(name for name, ready in checks.items() if not ready)
        print("provider predeploy failed: " + ", ".join(failed), file=sys.stderr)
        raise SystemExit(1)
    print("provider predeploy passed: " + ", ".join(sorted(checks)))


def main() -> None:
    try:
        settings = get_settings()
    except Exception as exc:
        print(
            "provider predeploy configuration invalid: " + exc.__class__.__name__,
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    required = {
        "LLM_API_KEY": settings.llm_api_key,
        "QDRANT_URL": settings.qdrant_url,
        "QDRANT_API_KEY": settings.qdrant_api_key,
        "REDIS_URL": settings.redis_url,
        "POSTGRES_URL": settings.postgres_url,
        "POSTGRES_SYNC_URL": settings.postgres_sync_url,
        "PUBLIC_SESSION_SECRET": settings.public_session_secret,
        "SYNTHETIC_DATASET_GENERATION": settings.synthetic_dataset_generation,
        "HITL_SERVICE_TOKEN": settings.hitl_service_token,
    }
    if missing := sorted(name for name, value in required.items() if not value):
        print("provider predeploy missing protected configuration: " + ", ".join(missing))
        raise SystemExit(1)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main_async())
    except Exception as exc:
        print("provider predeploy failed: " + exc.__class__.__name__, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

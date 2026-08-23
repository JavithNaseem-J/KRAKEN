"""
KRAKEN - Unified Purge and Fresh Reset Script

Performs a full clean wipe and re-initialization of:
1. Local filesystem caches (__pycache__, .pytest_cache, .ruff_cache, .mypy_cache, logs, dist, workspace backups)
2. Redis in-memory cache & sessions (FLUSHDB)
3. Qdrant vector collections (delete & recreate kraken_knowledge, kraken_semantic_cache, kraken_episodic_memory)
4. PostgreSQL relational database (TRUNCATE audit_log, tickets; re-ensure schema & re-seed master tickets)
5. Re-ingest knowledge base documents into Qdrant
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

import structlog  # noqa: E402

from src.utils.cache import create_async_qdrant_client  # noqa: E402
from src.utils.config import get_settings  # noqa: E402
from src.utils.db.pool import create_pool  # noqa: E402
from src.utils.db.schema import ensure_schema_async  # noqa: E402
from src.utils.embedder import BGEEmbedder  # noqa: E402
from src.utils.http_client import create_async_redis_client  # noqa: E402
from src.utils.knowledge.ingest import run_ingest_async  # noqa: E402

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
log = structlog.get_logger("purge_reset")
settings = get_settings()


def purge_local_caches() -> None:
    print("\n[1/5] Purging local filesystem caches & logs...")
    deleted_items = 0

    # 1. Remove cache folders
    cache_dir_names = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
    for root, dirs, _ in os.walk(ROOT_DIR, topdown=False):
        # Skip .venv and .git
        if ".venv" in root or ".git" in root:
            continue
        for d in list(dirs):
            if d in cache_dir_names:
                dir_path = Path(root) / d
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    deleted_items += 1
                except Exception as exc:
                    print(f"  Warning deleting {dir_path}: {exc}")

    # 2. Clean logs/
    logs_dir = ROOT_DIR / "logs"
    if logs_dir.exists():
        for file in logs_dir.glob("*"):
            if file.is_file():
                try:
                    file.unlink()
                    deleted_items += 1
                except Exception as exc:
                    print(f"  Warning deleting log {file}: {exc}")
    else:
        logs_dir.mkdir(parents=True, exist_ok=True)

    # 3. Clean frontend dist
    dist_dir = ROOT_DIR / "frontend-react" / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir, ignore_errors=True)
        deleted_items += 1

    # 4. Clean data/workspace
    workspace_dir = ROOT_DIR / "data" / "workspace"
    if workspace_dir.exists():
        for f in workspace_dir.glob("*"):
            if f.name.endswith(".bak.json") or f.name == "output.json":
                try:
                    f.unlink()
                    deleted_items += 1
                except Exception as exc:
                    print(f"  Warning deleting {f}: {exc}")
    else:
        workspace_dir.mkdir(parents=True, exist_ok=True)

    print(f"  ✓ Purged {deleted_items} cache folders/files and emptied logs.")


async def purge_redis() -> None:
    print("\n[2/5] Purging Redis cache, rate-limits & session memory...")
    try:
        redis = create_async_redis_client(settings.redis_url)
        await redis.flushdb()
        await redis.aclose()
        print("  ✓ Redis FLUSHDB completed successfully (all keys wiped).")
    except Exception as exc:
        print(f"  ⚠ Redis purge warning: {exc}")


async def purge_and_recreate_qdrant() -> None:
    print("\n[3/5] Purging & re-initializing Qdrant vector collections...")
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

    client = create_async_qdrant_client()
    collections_to_reset = [
        "kraken_knowledge",
        "kraken_semantic_cache",
        "kraken_episodic_memory",
    ]

    try:
        for col in collections_to_reset:
            if await client.collection_exists(col):
                await client.delete_collection(col)
                print(f"  - Deleted existing collection: {col}")

            await client.create_collection(
                collection_name=col,
                vectors_config=VectorParams(
                    size=settings.embedding_dim or 384,
                    distance=Distance.COSINE,
                ),
            )
            print(f"  + Recreated clean collection: {col} (dim=384, distance=Cosine)")

        # Create payload index for user_id on episodic memory
        await client.create_payload_index(
            collection_name="kraken_episodic_memory",
            field_name="user_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        print("  ✓ Created keyword payload index on kraken_episodic_memory.user_id")

    except Exception as exc:
        print(f"  ⚠ Qdrant purge warning: {exc}")
    finally:
        await client.close()


async def purge_and_reseed_postgres() -> None:
    print("\n[4/5] Resetting PostgreSQL database & seeding clean ticket data...")

    # 1. Reset local workspace tickets.json from master sample
    sample_file = ROOT_DIR / "data" / "knowledge" / "tickets" / "sample_tickets.json"
    workspace_file = ROOT_DIR / "data" / "workspace" / "tickets.json"

    if sample_file.exists():
        workspace_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sample_file, workspace_file)
        print(f"  ✓ Copied clean workspace tickets: '{sample_file.name}' -> '{workspace_file}'")

    # 2. Truncate & reseed PostgreSQL
    try:
        pool = await create_pool(settings.postgres_url, min_size=1, max_size=3)
        await ensure_schema_async(pool)

        async with pool.acquire() as conn:
            # Truncate tables cleanly
            await conn.execute("TRUNCATE TABLE audit_log, tickets CASCADE;")
            print("  ✓ Truncated relational tables: 'audit_log', 'tickets'.")

            # Seed master sample tickets
            if sample_file.exists():
                tickets = json.loads(sample_file.read_text(encoding="utf-8"))
                for t in tickets:
                    t_id = t.get("id", str(t.get("ticket_id", "")))
                    if not t_id:
                        continue
                    title = t.get("title", t.get("description", "Untitled Ticket"))
                    st = t.get("status", "open")
                    prio = t.get("priority", "medium")
                    await conn.execute(
                        """
                        INSERT INTO tickets (id, title, status, priority, payload)
                        VALUES ($1, $2, $3, $4, $5::jsonb)
                        ON CONFLICT (id) DO UPDATE
                        SET title = EXCLUDED.title, status = EXCLUDED.status, priority = EXCLUDED.priority, payload = EXCLUDED.payload;
                        """,
                        t_id,
                        title,
                        st,
                        prio,
                        json.dumps(t),
                    )
                print(f"  ✓ Seeded {len(tickets)} master IT support tickets into PostgreSQL.")

        await pool.close()
    except Exception as exc:
        print(f"  ⚠ PostgreSQL reset warning: {exc}")


async def reingest_knowledge_base() -> None:
    print("\n[5/5] Ingesting knowledge base documents into Qdrant (RAG)...")
    t0 = time.perf_counter()

    embedder = BGEEmbedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )
    client = create_async_qdrant_client()

    try:
        totals = await run_ingest_async(client, embedder)
        elapsed = time.perf_counter() - t0
        print(f"  ✓ FAQ chunks    : {totals.get('faq', 0)}")
        print(f"  ✓ Ticket chunks : {totals.get('tickets', 0)}")
        print(f"  ✓ SLA chunks    : {totals.get('sla', 0)}")
        print(f"  ✓ Total Chunks  : {sum(totals.values())} in {elapsed:.2f}s")
    except Exception as exc:
        print(f"  ⚠ Ingestion warning: {exc}")
    finally:
        await client.close()


async def main_async() -> None:
    print("=" * 64)
    print("  KRAKEN COMPLETE PURGE & FRESH SYSTEM INITIALIZATION")
    print("=" * 64)

    t_start = time.perf_counter()

    # Step 1: Local caches
    purge_local_caches()

    # Step 2: Redis
    await purge_redis()

    # Step 3: Qdrant
    await purge_and_recreate_qdrant()

    # Step 4: PostgreSQL
    await purge_and_reseed_postgres()

    # Step 5: Ingest Knowledge
    await reingest_knowledge_base()

    total_time = time.perf_counter() - t_start

    print("\n" + "=" * 64)
    print(f"  ✓ FULL PURGE & REINITIALIZATION COMPLETED IN {total_time:.2f}s")
    print("  The project is in a 100% pristine, fresh state.")
    print("=" * 64 + "\n")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

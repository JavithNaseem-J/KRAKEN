"""
asyncpg connection pool factory — shared across AKEA services.

Handles:
  - URL normalisation (SQLAlchemy format → asyncpg DSN)
  - pgvector type codec registration on every acquired connection
  - Configurable pool size and timeout
"""

from __future__ import annotations

import asyncpg
import structlog

log = structlog.get_logger(__name__)


def _asyncpg_dsn(url: str) -> str:
    """Strip SQLAlchemy dialect prefix so asyncpg can parse the DSN."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _register_codecs(conn: asyncpg.Connection) -> None:
    """Register pgvector codec on every new connection in the pool."""
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    except Exception:
        pass
    try:
        await conn.set_type_codec(
            "vector",
            schema="public",
            encoder=lambda v: "[" + ",".join(str(x) for x in v) + "]",
            decoder=lambda s: [float(x) for x in s.strip("[]").split(",")],
            format="text",
        )
    except Exception as exc:
        log.warning("db.codec_registration_failed", error=str(exc))


async def create_pool(
    postgres_url: str,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """
    Create and return an asyncpg connection pool.
    pgvector codec is registered automatically on every acquired connection.
    """
    dsn = _asyncpg_dsn(postgres_url)
    log.info("db.connecting", dsn=dsn.split("@")[-1] if "@" in dsn else dsn)

    pool = await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        init=_register_codecs,
        command_timeout=30,
        statement_cache_size=0,
    )
    log.info("db.pool_ready", min=min_size, max=max_size)
    return pool

from typing import Any

import asyncpg
import structlog

log = structlog.get_logger(__name__)


def _asyncpg_dsn(url: str) -> str:
    """Strip SQLAlchemy dialect prefix so asyncpg can parse the DSN."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def create_pool(
    postgres_url: str,
    min_size: int = 2,
    max_size: int = 10,
) -> asyncpg.Pool:
    """
    Create and return a standard asyncpg connection pool.
    """
    dsn = _asyncpg_dsn(postgres_url)
    log.info("db.connecting", dsn=dsn.split("@")[-1] if "@" in dsn else dsn)

    pool = await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=30,
        statement_cache_size=0,
    )
    log.info("db.pool_ready", min=min_size, max=max_size)
    return pool


create_async_pool = create_pool


def create_sync_pool(
    postgres_sync_url: str,
    min_size: int = 1,
    max_size: int = 10,
    max_idle: float = 300.0,
    timeout: float = 5.0,
    max_lifetime: float = 1800.0,
    connect_kwargs: dict[str, Any] | None = None,
) -> Any:
    """Create and return a sync psycopg_pool ConnectionPool."""
    try:
        from psycopg_pool import ConnectionPool

        kwargs = {"autocommit": True, **(connect_kwargs or {})}
        pool = ConnectionPool(
            conninfo=postgres_sync_url,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            max_idle=max_idle,
            max_lifetime=max_lifetime,
            open=True,
            kwargs=kwargs,
        )
        return pool
    except Exception as exc:
        log.warning("db.sync_pool_failed", error=str(exc))
        return None

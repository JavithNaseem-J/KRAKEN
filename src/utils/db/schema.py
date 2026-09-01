from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_SCHEMA_SQL_PATH = Path(__file__).with_name("schema.sql")


def _load_schema_sql() -> str:
    return _SCHEMA_SQL_PATH.read_text(encoding="utf-8")


SCHEMA_DDL = _load_schema_sql()


def _extract_section(sql: str, section_name: str) -> str:
    start = f"-- section:{section_name}:start"
    end = f"-- section:{section_name}:end"
    if start not in sql or end not in sql:
        raise RuntimeError(f"Schema section '{section_name}' is missing.")
    return sql.split(start, 1)[1].split(end, 1)[0].strip()


CREATE_TICKETS_TABLE_DDL = _extract_section(SCHEMA_DDL, "tickets")
CREATE_RUNTIME_METADATA_DDL = _extract_section(SCHEMA_DDL, "runtime-metadata")


async def ensure_schema_async(pool: Any) -> None:
    """Execute idempotent DDL statements against an asyncpg connection pool."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_DDL)
        log.info("db.ensure_schema_complete")
    except Exception as exc:
        log.warning("db.ensure_schema_failed", error=str(exc))


def ensure_schema_sync(pool: Any) -> None:
    """Execute idempotent DDL statements against a psycopg_pool ConnectionPool."""
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA_DDL)
            conn.commit()
        log.info("db.ensure_schema_sync_complete")
    except Exception as exc:
        log.warning("db.ensure_schema_sync_failed", error=str(exc))

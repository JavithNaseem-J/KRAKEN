from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


async def ensure_schema_async(pool: Any) -> None:
    """Execute idempotent DDL statements against an asyncpg connection pool."""
    ddl = """
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";

    CREATE TABLE IF NOT EXISTS audit_log (
        id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        timestamp     TIMESTAMPTZ NOT NULL    DEFAULT NOW(),
        session_id    VARCHAR(64) NOT NULL,
        user_id       VARCHAR(64) NOT NULL,
        action_type   VARCHAR(32) NOT NULL,
        action_name   VARCHAR(64) NOT NULL,
        risk_level    VARCHAR(16) NOT NULL,
        hitl_required BOOLEAN     NOT NULL,
        hitl_decision VARCHAR(16),
        status        VARCHAR(16) NOT NULL,
        payload       JSONB,
        result        JSONB,
        reasoning     TEXT,
        previous_hash VARCHAR(64) NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
        entry_hash    VARCHAR(64)
    );

    CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_log_session ON audit_log (session_id, timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id, timestamp DESC);

    CREATE TABLE IF NOT EXISTS tickets (
        id VARCHAR(64) PRIMARY KEY,
        title TEXT,
        status VARCHAR(32) NOT NULL DEFAULT 'open',
        priority VARCHAR(32) NOT NULL DEFAULT 'medium',
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(ddl)
        log.info("db.ensure_schema_complete")
    except Exception as exc:
        log.warning("db.ensure_schema_failed", error=str(exc))


def ensure_schema_sync(pool: Any) -> None:
    """Execute idempotent DDL statements against a psycopg_pool ConnectionPool."""
    ddl = """
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";

    CREATE TABLE IF NOT EXISTS audit_log (
        id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        timestamp     TIMESTAMPTZ NOT NULL    DEFAULT NOW(),
        session_id    VARCHAR(64) NOT NULL,
        user_id       VARCHAR(64) NOT NULL,
        action_type   VARCHAR(32) NOT NULL,
        action_name   VARCHAR(64) NOT NULL,
        risk_level    VARCHAR(16) NOT NULL,
        hitl_required BOOLEAN     NOT NULL,
        hitl_decision VARCHAR(16),
        status        VARCHAR(16) NOT NULL,
        payload       JSONB,
        result        JSONB,
        reasoning     TEXT,
        previous_hash VARCHAR(64) NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
        entry_hash    VARCHAR(64)
    );

    CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_log_session ON audit_log (session_id, timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id, timestamp DESC);

    CREATE TABLE IF NOT EXISTS tickets (
        id VARCHAR(64) PRIMARY KEY,
        title TEXT,
        status VARCHAR(32) NOT NULL DEFAULT 'open',
        priority VARCHAR(32) NOT NULL DEFAULT 'medium',
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(ddl)
            conn.commit()
        log.info("db.ensure_schema_sync_complete")
    except Exception as exc:
        log.warning("db.ensure_schema_sync_failed", error=str(exc))

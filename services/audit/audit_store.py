"""
Audit store — append-only writes to PostgreSQL audit_log table.

Table schema (from scripts/init.sql):
  audit_log(
    id            SERIAL PRIMARY KEY,
    timestamp     TIMESTAMPTZ DEFAULT NOW(),
    session_id    TEXT,
    user_id       TEXT,
    action_type   TEXT,           -- "READ" | "WRITE"
    action_name   TEXT,
    risk_level    TEXT,           -- "SAFE" | "CRITICAL"
    hitl_required BOOLEAN,
    hitl_decision TEXT,           -- "approved" | "rejected" | "timeout" | NULL
    status        TEXT,           -- "success" | "failure"
    reasoning     TEXT,
    payload       JSONB,
    result        JSONB
  )

The table has CREATE RULE statements that block UPDATE and DELETE,
making it append-only at the database level. No application-level flag
can override this — even if the service has DB write permissions,
altering past records is rejected by the rule.

The pool is created externally (in lifespan) and passed in.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class AuditStore:
    """
    Writes audit log entries to PostgreSQL.
    All writes are INSERTs — no updates, no deletes (enforced by DB rules).
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def log_action(
        self,
        session_id:    str,
        user_id:       str,
        action_type:   str,
        action_name:   str,
        risk_level:    str,
        hitl_required: bool,
        status:        str,
        reasoning:     str | None       = None,
        payload:       dict | None      = None,
        result:        dict | None      = None,
        hitl_decision: str | None       = None,
    ) -> int:
        """
        Insert one audit record. Returns the new row id.
        Raises on DB failure — caller decides how to handle (usually log + ignore).
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO audit_log (
                    session_id, user_id, action_type, action_name,
                    risk_level, hitl_required, hitl_decision, status,
                    reasoning, payload, result
                )
                VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8,
                    $9, $10::jsonb, $11::jsonb
                )
                RETURNING id
                """,
                session_id,
                user_id,
                action_type,
                action_name,
                risk_level,
                hitl_required,
                hitl_decision,
                status,
                reasoning,
                json.dumps(payload or {}),
                json.dumps(result or {}),
            )

        row_id = row["id"]
        log.info(
            "audit.logged",
            id=row_id,
            session_id=session_id,
            action=action_name,
            status=status,
            risk=risk_level,
        )
        return row_id

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return audit records for a session (newest first). Read-only."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, timestamp, action_type, action_name, risk_level,
                       hitl_required, hitl_decision, status, user_id
                FROM   audit_log
                WHERE  session_id = $1
                ORDER  BY timestamp DESC
                LIMIT  $2
                """,
                session_id,
                limit,
            )

        return [
            {
                "id":            row["id"],
                "timestamp":     row["timestamp"].isoformat(),
                "action_type":   row["action_type"],
                "action_name":   row["action_name"],
                "risk_level":    row["risk_level"],
                "hitl_required": row["hitl_required"],
                "hitl_decision": row["hitl_decision"],
                "status":        row["status"],
                "user_id":       row["user_id"],
            }
            for row in rows
        ]

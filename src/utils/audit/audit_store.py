from __future__ import annotations

import hashlib
import json
from typing import Any

import asyncpg
import structlog

from src.utils.config import get_settings
from src.utils.logging import summarize_audit_data
from src.utils.models.audit import AuditLogRequest

log = structlog.get_logger(__name__)

_GENESIS_HASH = "0" * 64


class AuditStore:
    """
    Writes audit log entries to PostgreSQL.
    All writes are INSERTs with SHA-256 cryptographic hash chaining (previous_hash -> entry_hash).
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._dataset_generation = get_settings().synthetic_dataset_generation

    async def log_action(self, entry: AuditLogRequest) -> str:
        """
        Insert one audit record with SHA-256 hash chain link. Returns the new row id (UUID/string).
        Raises on DB failure — caller decides how to handle.
        """
        entry = entry.model_copy(
            update={
                "payload": summarize_audit_data(entry.payload),
                "result": summarize_audit_data(entry.result),
            }
        )
        payload_str = json.dumps(entry.payload or {}, sort_keys=True)
        result_str = json.dumps(entry.result or {}, sort_keys=True)

        async with (
            self._pool.acquire() as conn,
            conn.transaction(isolation="serializable"),
        ):
            await conn.execute("DELETE FROM audit_log WHERE expires_at <= NOW()")
            # 1. Fetch previous entry_hash to form hash chain
            prev_row = await conn.fetchrow(
                "SELECT entry_hash FROM audit_log WHERE entry_hash IS NOT NULL ORDER BY timestamp DESC, id DESC LIMIT 1"
            )
            previous_hash = (
                prev_row["entry_hash"] if prev_row and prev_row["entry_hash"] else _GENESIS_HASH
            )

            # 2. Compute current entry_hash
            raw_chain_string = (
                f"{previous_hash}:{self._dataset_generation}:{entry.session_id}:"
                f"{entry.user_id}:{entry.action_name}:{entry.status}:{payload_str}"
            )
            entry_hash = hashlib.sha256(raw_chain_string.encode("utf-8")).hexdigest()

            row = await conn.fetchrow(
                """
                    INSERT INTO audit_log (
                        session_id, user_id, action_type, action_name,
                        risk_level, hitl_required, hitl_decision, status,
                        payload, result, previous_hash, entry_hash, dataset_generation
                    )
                    VALUES (
                        $1, $2, $3, $4,
                        $5, $6, $7, $8,
                        $9::jsonb, $10::jsonb, $11, $12, $13
                    )
                    RETURNING id
                    """,
                entry.session_id,
                entry.user_id,
                entry.action_type,
                entry.action_name,
                entry.risk_level,
                entry.hitl_required,
                entry.hitl_decision,
                entry.status,
                payload_str,
                result_str,
                previous_hash,
                entry_hash,
                self._dataset_generation,
            )

        row_id = row["id"]
        log.info(
            "audit.logged",
            id=row_id,
            session_id=entry.session_id,
            action=entry.action_name,
            status=entry.status,
            entry_hash=entry_hash[:12],
        )
        return str(row_id)

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
                WHERE  session_id = $1 AND dataset_generation = $2
                ORDER  BY timestamp DESC
                LIMIT  $3
                """,
                session_id,
                self._dataset_generation,
                limit,
            )

        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"].isoformat(),
                "action_type": row["action_type"],
                "action_name": row["action_name"],
                "risk_level": row["risk_level"],
                "hitl_required": row["hitl_required"],
                "hitl_decision": row["hitl_decision"],
                "status": row["status"],
                "user_id": row["user_id"],
            }
            for row in rows
        ]

    async def get_user_history(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent audit records for a user across all sessions."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, timestamp, session_id, action_name, risk_level,
                       hitl_required, hitl_decision, status
                FROM   audit_log
                WHERE  user_id = $1 AND dataset_generation = $2
                ORDER  BY timestamp DESC
                LIMIT  $3
                """,
                user_id,
                self._dataset_generation,
                limit,
            )

        records = [dict(r) for r in rows]
        for r in records:
            if "timestamp" in r:
                r["timestamp"] = r["timestamp"].isoformat()
        return records

    async def verify_chain(self, page_size: int = 500) -> dict[str, Any]:
        """
        Recompute SHA-256 hash chains using keyset pagination (500 records/page).
        Returns {"valid": True, "count": N} or {"valid": False, "broken_at_id": id, ...}.
        """
        previous_hash: str | None = None
        total_count = 0
        last_timestamp = None
        last_id = None

        async with self._pool.acquire() as conn:
            while True:
                if last_timestamp is None:
                    rows = await conn.fetch(
                        """
                        SELECT id, timestamp, session_id, user_id, action_name, status, payload, previous_hash, entry_hash
                        FROM audit_log
                        WHERE dataset_generation = $2
                        ORDER BY timestamp ASC, id ASC
                        LIMIT $1
                        """,
                        page_size,
                        self._dataset_generation,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, timestamp, session_id, user_id, action_name, status, payload, previous_hash, entry_hash
                        FROM audit_log
                        WHERE (timestamp, id) > ($1, $2)
                          AND dataset_generation = $4
                        ORDER BY timestamp ASC, id ASC
                        LIMIT $3
                        """,
                        last_timestamp,
                        last_id,
                        page_size,
                        self._dataset_generation,
                    )

                if not rows:
                    break

                for row in rows:
                    total_count += 1
                    if previous_hash is None:
                        previous_hash = row["previous_hash"] or _GENESIS_HASH
                    payload_data = row["payload"]
                    if isinstance(payload_data, str):
                        try:
                            payload_data = json.loads(payload_data)
                        except Exception:
                            payload_data = {}
                    p_str = json.dumps(payload_data or {}, sort_keys=True)

                    raw = (
                        f"{previous_hash}:{self._dataset_generation}:{row['session_id']}:"
                        f"{row['user_id']}:{row['action_name']}:{row['status']}:{p_str}"
                    )
                    computed = hashlib.sha256(raw.encode("utf-8")).hexdigest()

                    if row["previous_hash"] and row["previous_hash"] != previous_hash:
                        return {
                            "valid": False,
                            "broken_at_id": str(row["id"]),
                            "reason": "previous_hash mismatch",
                        }
                    if row["entry_hash"] and row["entry_hash"] != computed:
                        return {
                            "valid": False,
                            "broken_at_id": str(row["id"]),
                            "reason": "entry_hash mismatch",
                        }

                    previous_hash = row["entry_hash"] if row["entry_hash"] else previous_hash
                    last_timestamp = row["timestamp"]
                    last_id = row["id"]

        return {"valid": True, "count": total_count}

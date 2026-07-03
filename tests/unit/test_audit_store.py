"""
Unit tests for the AuditStore.
Mocks the asyncpg pool — zero real DB dependency.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.audit.audit_store import AuditStore


def _make_store() -> tuple[AuditStore, MagicMock]:
    """Return (AuditStore, mock_pool) for use in tests."""
    pool = MagicMock()
    conn = AsyncMock()

    # pool.acquire() returns an async context manager that yields conn
    conn_ctx = AsyncMock()
    conn_ctx.__aenter__ = AsyncMock(return_value=conn)
    conn_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=conn_ctx)

    return AuditStore(pool), conn


class TestLogAction:
    async def test_returns_row_id(self) -> None:
        store, conn = _make_store()
        conn.fetchrow = AsyncMock(return_value={"id": 42})

        row_id = await store.log_action(
            session_id="s1", user_id="u1", action_type="READ",
            action_name="read_ticket", risk_level="SAFE",
            hitl_required=False, status="success",
        )
        assert row_id == 42

    async def test_insert_called_once(self) -> None:
        store, conn = _make_store()
        conn.fetchrow = AsyncMock(return_value={"id": 1})

        await store.log_action(
            session_id="s1", user_id="u1", action_type="WRITE",
            action_name="write_json_file", risk_level="CRITICAL",
            hitl_required=True, status="success", hitl_decision="approved",
        )
        conn.fetchrow.assert_called_once()

    async def test_none_payload_handled(self) -> None:
        """None payload / result should not crash the INSERT (serialised to '{}')."""
        store, conn = _make_store()
        conn.fetchrow = AsyncMock(return_value={"id": 5})

        await store.log_action(
            session_id="s1", user_id="u1", action_type="READ",
            action_name="read_ticket_list", risk_level="SAFE",
            hitl_required=False, status="success",
            payload=None, result=None,
        )
        conn.fetchrow.assert_called_once()


class TestGetSessionHistory:
    async def test_returns_records(self) -> None:
        store, conn = _make_store()
        from datetime import datetime, timezone
        conn.fetch = AsyncMock(return_value=[
            {
                "id": 1, "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "action_type": "READ", "action_name": "read_ticket",
                "risk_level": "SAFE", "hitl_required": False,
                "hitl_decision": None, "status": "success", "user_id": "u1",
            }
        ])
        records = await store.get_session_history("s1", limit=10)
        assert len(records) == 1
        assert records[0]["action_name"] == "read_ticket"
        assert isinstance(records[0]["timestamp"], str)   # ISO formatted

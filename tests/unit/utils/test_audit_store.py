from __future__ import annotations

import json
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

from src.utils.audit.audit_store import AuditStore
from src.utils.models.audit import AuditLogRequest


def _make_store() -> tuple[AuditStore, MagicMock]:
    """Return (AuditStore, mock_pool) for use in tests."""
    pool = MagicMock()
    conn = AsyncMock()

    # pool.acquire() returns an async context manager that yields conn
    conn_ctx = AsyncMock()
    conn_ctx.__aenter__ = AsyncMock(return_value=conn)
    conn_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=conn_ctx)

    # conn.transaction() returns an async context manager for serializable transactions
    txn_ctx = AsyncMock()
    txn_ctx.__aenter__ = AsyncMock(return_value=None)
    txn_ctx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn_ctx)

    return AuditStore(pool), conn


class TestLogAction:
    async def test_returns_row_id(self) -> None:
        store, conn = _make_store()
        conn.fetchrow = AsyncMock(side_effect=[None, {"id": 42}])

        row_id = await store.log_action(
            AuditLogRequest(
                session_id="s1",
                user_id="u1",
                action_type="READ",
                action_name="read_ticket",
                risk_level="SAFE",
                hitl_required=False,
                status="success",
            )
        )
        assert row_id == "42"
        assert conn.fetchrow.call_count == 2
        # Verify SQL insert arguments contain entry_hash
        insert_args = conn.fetchrow.call_args_list[1].args
        assert len(insert_args[12]) == 64  # SHA-256 hex digest length

    async def test_insert_called_once(self) -> None:
        store, conn = _make_store()
        conn.fetchrow = AsyncMock(side_effect=[None, {"id": 1}])

        await store.log_action(
            AuditLogRequest(
                session_id="s1",
                user_id="u1",
                action_type="WRITE",
                action_name="write_json_file",
                risk_level="CRITICAL",
                hitl_required=True,
                status="success",
                hitl_decision="approved",
            )
        )
        assert conn.fetchrow.call_count == 2

    async def test_none_payload_handled(self) -> None:
        """None payload / result should not crash the INSERT (serialised to '{}')."""
        store, conn = _make_store()
        conn.fetchrow = AsyncMock(side_effect=[None, {"id": 5}])

        await store.log_action(
            AuditLogRequest(
                session_id="s1",
                user_id="u1",
                action_type="READ",
                action_name="read_ticket_list",
                risk_level="SAFE",
                hitl_required=False,
                status="success",
                payload=None,
                result=None,
            )
        )
        assert conn.fetchrow.call_count == 2

    async def test_payload_is_reduced_to_redacted_metadata(self) -> None:
        store, conn = _make_store()
        conn.fetchrow = AsyncMock(side_effect=[None, {"id": 6}])

        await store.log_action(
            AuditLogRequest(
                session_id="s1",
                user_id="u1",
                action_type="WRITE",
                action_name="create_ticket",
                risk_level="SAFE",
                hitl_required=False,
                status="success",
                payload={"description": "private content", "user_name": "Visitor"},
            )
        )

        insert_args = conn.fetchrow.call_args_list[1].args
        assert json.loads(insert_args[9]) == {"fields": ["description", "user_name"]}
        conn.execute.assert_awaited_once()


class TestGetSessionHistory:
    async def test_returns_records(self) -> None:
        store, conn = _make_store()
        from datetime import datetime

        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "action_type": "READ",
                    "action_name": "read_ticket",
                    "risk_level": "SAFE",
                    "hitl_required": False,
                    "hitl_decision": None,
                    "status": "success",
                    "user_id": "u1",
                }
            ]
        )
        records = await store.get_session_history("s1", limit=10)
        assert len(records) == 1
        assert records[0]["action_name"] == "read_ticket"
        assert isinstance(records[0]["timestamp"], str)  # ISO formatted


class TestGetUserHistory:
    async def test_returns_user_records(self) -> None:
        store, conn = _make_store()
        from datetime import datetime

        conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "session_id": "s1",
                    "action_name": "escalate",
                    "risk_level": "CRITICAL",
                    "hitl_required": True,
                    "hitl_decision": "approved",
                    "status": "success",
                }
            ]
        )
        records = await store.get_user_history("u1", limit=10)
        assert len(records) == 1
        assert records[0]["action_name"] == "escalate"
        assert isinstance(records[0]["timestamp"], str)

from src.utils.db.schema import (
    CREATE_TICKETS_TABLE_DDL,
    SCHEMA_DDL,
    ensure_schema_async,
    ensure_schema_sync,
)


class _AsyncConn:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, sql: str) -> None:
        self.executed.append(sql)


class _AsyncAcquire:
    def __init__(self, conn: _AsyncConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _AsyncConn:
        return self.conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _AsyncPool:
    def __init__(self) -> None:
        self.conn = _AsyncConn()

    def acquire(self) -> _AsyncAcquire:
        return _AsyncAcquire(self.conn)


class _SyncCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def __enter__(self) -> "_SyncCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _SyncConn:
    def __init__(self) -> None:
        self.cursor_obj = _SyncCursor()
        self.committed = False

    def cursor(self) -> _SyncCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> "_SyncConn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _SyncPool:
    def __init__(self) -> None:
        self.conn = _SyncConn()

    def connection(self) -> _SyncConn:
        return self.conn


async def test_async_and_sync_schema_initializers_use_same_schema_source():
    async_pool = _AsyncPool()
    sync_pool = _SyncPool()

    await ensure_schema_async(async_pool)
    ensure_schema_sync(sync_pool)

    assert async_pool.conn.executed == [SCHEMA_DDL]
    assert sync_pool.conn.cursor_obj.executed == [SCHEMA_DDL]
    assert sync_pool.conn.committed is True


def test_ticket_table_ddl_is_extracted_from_full_schema():
    assert "CREATE TABLE IF NOT EXISTS tickets" in CREATE_TICKETS_TABLE_DDL
    assert CREATE_TICKETS_TABLE_DDL in SCHEMA_DDL
    assert "audit_log_no_update" in SCHEMA_DDL
    assert "audit_log_no_delete" in SCHEMA_DDL

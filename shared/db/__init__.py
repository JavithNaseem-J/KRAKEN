"""
Shared database utilities package.
"""

from shared.db.pool import (
    create_async_pool,
    create_pool,
    create_sync_pool,
)
from shared.db.schema import ensure_schema_async, ensure_schema_sync
from shared.db.tickets import (
    CREATE_TICKETS_TABLE_DDL,
    ensure_tickets_table,
    seed_tickets,
)

__all__ = [
    "create_pool",
    "create_async_pool",
    "create_sync_pool",
    "ensure_schema_async",
    "ensure_schema_sync",
    "CREATE_TICKETS_TABLE_DDL",
    "ensure_tickets_table",
    "seed_tickets",
]

from __future__ import annotations

import json
from typing import Any

import structlog

log = structlog.get_logger(__name__)

CREATE_TICKETS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS tickets (
    id VARCHAR(64) PRIMARY KEY,
    title TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    priority VARCHAR(32) NOT NULL DEFAULT 'medium',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_tickets_table(conn: Any) -> None:
    """Ensure the tickets table exists in PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TICKETS_TABLE_DDL)
    conn.commit()


def seed_tickets(conn: Any, tickets: list[dict[str, Any]], update_on_conflict: bool = True) -> int:
    """
    Insert or update tickets in PostgreSQL.
    Returns the number of seeded tickets.
    """
    ensure_tickets_table(conn)

    on_conflict_clause = (
        """
        ON CONFLICT (id) DO UPDATE
        SET title = EXCLUDED.title, status = EXCLUDED.status, priority = EXCLUDED.priority, payload = EXCLUDED.payload;
        """
        if update_on_conflict
        else "ON CONFLICT (id) DO NOTHING;"
    )

    query = f"""
        INSERT INTO tickets (id, title, status, priority, payload)
        VALUES (%s, %s, %s, %s, %s)
        {on_conflict_clause}
    """

    count = 0
    with conn.cursor() as cur:
        for t in tickets:
            t_id = t.get("id", str(t.get("ticket_id", "")))
            if not t_id:
                continue
            title = t.get("title", t.get("description", ""))
            status = t.get("status", "open")
            priority = t.get("priority", "medium")
            cur.execute(query, (t_id, title, status, priority, json.dumps(t)))
            count += 1
    conn.commit()
    return count

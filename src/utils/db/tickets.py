from __future__ import annotations

import json
from typing import Any

import structlog

from src.utils.db.schema import CREATE_RUNTIME_METADATA_DDL, CREATE_TICKETS_TABLE_DDL

log = structlog.get_logger(__name__)


def ensure_tickets_table(conn: Any) -> None:
    """Ensure the tickets table exists in PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute(CREATE_RUNTIME_METADATA_DDL)
        cur.execute(CREATE_TICKETS_TABLE_DDL)
    conn.commit()


def seed_tickets(
    conn: Any,
    tickets: list[dict[str, Any]],
    update_on_conflict: bool = True,
    *,
    activate: bool = True,
) -> int:
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

    generations = {str(ticket.get("dataset_generation") or "") for ticket in tickets}
    generations.discard("")
    if len(generations) > 1:
        raise ValueError("ticket seed contains multiple dataset generations")

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
        if generations:
            generation = next(iter(generations))
            cur.execute(
                """
                INSERT INTO kraken_runtime_metadata (key, value, updated_at)
                VALUES ('synthetic_dataset_generation', %s, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at;
                """,
                (generation,),
            )
            if activate:
                cur.execute(
                    """
                    INSERT INTO kraken_runtime_metadata (key, value, updated_at)
                    VALUES ('synthetic_dataset_state', 'active', NOW())
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at;
                    """
                )
    conn.commit()
    return count

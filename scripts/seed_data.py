from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

SAMPLE_TICKETS_FILE = (
    Path(__file__).parent.parent / "data" / "knowledge" / "tickets" / "sample_tickets.json"
)
WORKSPACE_TICKETS_FILE = Path(__file__).parent.parent / "data" / "workspace" / "tickets.json"


ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def seed_postgres() -> None:
    pg_url = os.getenv("POSTGRES_URL", os.getenv("DATABASE_URL"))
    if not pg_url:
        return

    try:
        from psycopg_pool import ConnectionPool

        from src.utils.db.tickets import seed_tickets

        with ConnectionPool(conninfo=pg_url, timeout=5) as pool, pool.connection() as conn:
            if SAMPLE_TICKETS_FILE.exists():
                tickets = json.loads(SAMPLE_TICKETS_FILE.read_text(encoding="utf-8"))
                count = seed_tickets(conn, tickets, update_on_conflict=True)
                print(f"Successfully seeded PostgreSQL tickets table ({count} rows).")
    except Exception as exc:
        print(f"PostgreSQL seed warning: {exc}")


def main() -> None:
    if not SAMPLE_TICKETS_FILE.exists():
        print(f"Error: Master tickets file not found at '{SAMPLE_TICKETS_FILE}'.")
        sys.exit(1)

    WORKSPACE_TICKETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_TICKETS_FILE, WORKSPACE_TICKETS_FILE)
    print(
        f"Successfully copied ticket database: '{SAMPLE_TICKETS_FILE}' -> '{WORKSPACE_TICKETS_FILE}'"
    )

    seed_postgres()


if __name__ == "__main__":
    main()

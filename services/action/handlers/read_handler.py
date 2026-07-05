"""
Read Action Handler — serves READ actions against the ticket knowledge base.

Data source: data/knowledge/tickets/*.json and *.csv files.
These are the same files ingested into ChromaDB by the ticket_loader,
so the data is always consistent.

Why not PostgreSQL here?
  PostgreSQL structured reads are wired in Phase 6 (async SQLAlchemy engine).
  Reading from the JSON source files is correct, fast, and has zero infra
  dependency — making the action service fully testable without a DB.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import structlog

from shared.exceptions import ActionExecutionError

log = structlog.get_logger(__name__)

_TICKETS_DIR = Path(__file__).resolve().parents[4] / "data" / "knowledge" / "tickets"


def _load_all_tickets() -> list[dict[str, Any]]:
    """Load every ticket from all JSON and CSV files in the tickets directory."""
    if not _TICKETS_DIR.exists():
        return []

    all_tickets: list[dict[str, Any]] = []

    for file_path in sorted(_TICKETS_DIR.iterdir()):
        try:
            if file_path.suffix.lower() == ".json":
                data = json.loads(file_path.read_text(encoding="utf-8"))
                all_tickets.extend(data if isinstance(data, list) else [data])
            elif file_path.suffix.lower() == ".csv":
                with file_path.open(encoding="utf-8", newline="") as f:
                    all_tickets.extend(list(csv.DictReader(f)))
        except Exception as exc:
            log.error("read_handler.load_error", file=file_path.name, error=str(exc))

    return all_tickets


def read_ticket(ticket_id: str) -> dict[str, Any]:
    """
    Retrieve a single ticket by ID.

    Args:
        ticket_id: The ticket identifier (e.g. "TK-001").

    Returns:
        Ticket dict if found.

    Raises:
        ActionExecutionError: If the ticket is not found.
    """
    if not ticket_id or not ticket_id.strip():
        raise ActionExecutionError("ticket_id cannot be empty.")

    tickets = _load_all_tickets()
    ticket_id_norm = ticket_id.strip().upper()

    for ticket in tickets:
        tid = str(ticket.get("id", "")).strip().upper()
        if tid == ticket_id_norm:
            log.info("read_handler.read_ticket", ticket_id=ticket_id)
            return ticket

    raise ActionExecutionError(
        f"Ticket '{ticket_id}' not found.",
        details={"available_count": len(tickets)},
    )


def read_ticket_list(
    status: str | None = None,
    priority: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    List tickets with optional filters.

    Args:
        status:   Filter by status (e.g. "open", "resolved").
        priority: Filter by priority (e.g. "high", "critical").
        category: Filter by category (e.g. "network", "email").
        limit:    Maximum number of tickets to return (1–100).

    Returns:
        List of matching ticket dicts.
    """
    limit = max(1, min(limit, 100))  # Clamp to 1-100
    tickets = _load_all_tickets()

    filtered = [
        t
        for t in tickets
        if (status is None or str(t.get("status", "")).lower() == status.lower())
        and (priority is None or str(t.get("priority", "")).lower() == priority.lower())
        and (category is None or str(t.get("category", "")).lower() == category.lower())
    ]

    log.info(
        "read_handler.read_ticket_list",
        total=len(tickets),
        filtered=len(filtered),
        status=status,
        priority=priority,
        category=category,
    )
    return filtered[:limit]

"""
Ticket history loader.
Reads .json and .csv files from data/knowledge/tickets/.
Converts tickets into human-readable text representations for semantic search.
"""

from __future__ import annotations

from typing import Any

from src.utils.models.knowledge import TicketDocument

from .base import load_structured_chunks, resolve_data_dir

TICKETS_DIR = resolve_data_dir("tickets")


def _ticket_to_text(ticket_raw: dict[str, Any]) -> str:
    """Convert a ticket record to a natural-language text chunk via TicketDocument validation."""
    ticket = TicketDocument.model_validate(ticket_raw)
    parts = [
        f"Ticket ID: {ticket.ticket_id}",
        f"Subject: {ticket.subject}",
        f"Status: {ticket.status}",
        f"Priority: {ticket.priority}",
        f"Category: {ticket.category}",
    ]
    if ticket.description:
        parts.append(f"Description: {ticket.description}")
    if ticket.resolved_at:
        parts.append(f"Resolved at: {ticket.resolved_at}")
    return "\n".join(p for p in parts if p.split(": ", 1)[1])


def load_ticket_chunks() -> list[dict[str, Any]]:
    """Load all ticket records from JSON and CSV files."""
    return load_structured_chunks(
        data_dir=TICKETS_DIR,
        allowed_suffixes={".json", ".csv"},
        record_to_text=_ticket_to_text,
        id_prefix="tickets",
    )

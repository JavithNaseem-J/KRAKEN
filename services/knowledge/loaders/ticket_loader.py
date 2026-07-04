"""
Ticket history loader.

Reads .json and .csv files from data/knowledge/tickets/.
Each ticket is converted to a human-readable text representation
for semantic search, plus its raw structured form for exact lookups.

Returns:
  chunks  — ChromaDB-ready dicts (for semantic search)
  records — raw ticket dicts (for PostgreSQL upsert)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

TICKETS_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "tickets"


def _ticket_to_text(ticket: dict[str, Any]) -> str:
    """Convert a ticket record to a natural-language text chunk."""
    parts = [
        f"Ticket ID: {ticket.get('id', 'unknown')}",
        f"Title: {ticket.get('title', '')}",
        f"Status: {ticket.get('status', '')}",
        f"Priority: {ticket.get('priority', '')}",
        f"Category: {ticket.get('category', '')}",
    ]
    if desc := ticket.get("description"):
        parts.append(f"Description: {desc}")
    if resolved := ticket.get("resolved_at"):
        parts.append(f"Resolved at: {resolved}")
    return "\n".join(p for p in parts if p.split(": ", 1)[1])


def _load_json_file(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else [data]
    except Exception as exc:
        log.error("ticket_loader.json_error", path=str(path), error=str(exc))
        return []


def _load_csv_file(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except Exception as exc:
        log.error("ticket_loader.csv_error", path=str(path), error=str(exc))
        return []


def load_ticket_chunks() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Load all ticket history files.

    Returns:
        (chunks, records)
        chunks  — ChromaDB-ready dicts for semantic search
        records — raw ticket dicts for PostgreSQL upsert
    """
    if not TICKETS_DIR.exists():
        log.warning("ticket_loader.dir_missing", path=str(TICKETS_DIR))
        return [], []

    supported = {".json", ".csv"}
    files = [f for f in TICKETS_DIR.iterdir() if f.suffix.lower() in supported]

    if not files:
        log.warning("ticket_loader.no_files", path=str(TICKETS_DIR))
        return [], []

    all_records: list[dict[str, Any]] = []

    for file_path in sorted(files):
        log.info("ticket_loader.loading", file=file_path.name)
        if file_path.suffix.lower() == ".json":
            records = _load_json_file(file_path)
        else:
            records = _load_csv_file(file_path)
        all_records.extend(records)

    # Build ChromaDB chunks (one chunk per ticket)
    chunks: list[dict[str, Any]] = []
    for ticket in all_records:
        ticket_id = str(ticket.get("id", ""))
        if not ticket_id:
            continue
        chunks.append({
            "id":       f"ticket_{ticket_id}",
            "document": _ticket_to_text(ticket),
            "metadata": {
                "source":    "tickets",
                "ticket_id": ticket_id,
                "status":    str(ticket.get("status", "")),
                "priority":  str(ticket.get("priority", "")),
                "category":  str(ticket.get("category", "")),
            },
        })

    log.info(
        "ticket_loader.complete",
        total_tickets=len(all_records),
        total_chunks=len(chunks),
    )
    return chunks, all_records

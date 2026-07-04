"""
Ticket Action Handlers — executes ticket triage operations on the active database.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

from shared.exceptions import ActionExecutionError
from ..safety.path_validator import WORKSPACE_ROOT

log = structlog.get_logger(__name__)

_TICKETS_FILE = WORKSPACE_ROOT / "tickets.json"
_SEED_FILE = Path(__file__).resolve().parents[4] / "data" / "knowledge" / "tickets" / "sample_tickets.json"


def _load_tickets() -> list[dict[str, Any]]:
    """Load tickets from active workspace or fall back to seed file."""
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    
    if not _TICKETS_FILE.exists():
        if _SEED_FILE.exists():
            try:
                content = _SEED_FILE.read_text(encoding="utf-8")
                _TICKETS_FILE.write_text(content, encoding="utf-8")
                log.info("ticket_handler.init_workspace_db", src=str(_SEED_FILE), dest=str(_TICKETS_FILE))
            except Exception as exc:
                log.error("ticket_handler.init_db_error", error=str(exc))
                return []
        else:
            log.warning("ticket_handler.no_db_found")
            return []

    try:
        data = json.loads(_TICKETS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        log.error("ticket_handler.load_error", error=str(exc))
        raise ActionExecutionError(f"Failed to load ticket database: {exc}")


def _save_tickets(tickets: list[dict[str, Any]]) -> None:
    """Atomic write of updated tickets list to the workspace."""
    try:
        json_bytes = json.dumps(tickets, indent=2, ensure_ascii=False).encode("utf-8")
        
        # Write to temp file first to ensure atomic swap
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=WORKSPACE_ROOT,
            prefix=".tmp_tickets_",
            suffix=".json",
        )
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(json_bytes)
            os.replace(tmp_path, _TICKETS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        log.error("ticket_handler.save_error", error=str(exc))
        raise ActionExecutionError(f"Failed to write ticket database: {exc}")


def execute_auto_respond(ticket_id: str | None, response_text: str, evidence: str) -> dict[str, Any]:
    """Auto-respond to a ticket or general question, citing specific evidence."""
    if not response_text or not response_text.strip():
        raise ActionExecutionError("response_text cannot be empty.")
    if not evidence or not evidence.strip():
        raise ActionExecutionError("evidence (cited fact from knowledge base) must be provided.")

    result_meta: dict[str, Any] = {
        "response": response_text,
        "evidence_cited": evidence,
        "action": "auto_respond"
    }

    if ticket_id:
        tickets = _load_tickets()
        ticket_id_norm = ticket_id.strip().upper()
        found = False
        for ticket in tickets:
            if str(ticket.get("id", "")).strip().upper() == ticket_id_norm:
                ticket["status"] = "resolved"
                ticket["resolution_response"] = response_text
                ticket["evidence_cited"] = evidence
                found = True
                break
        if not found:
            raise ActionExecutionError(f"Ticket '{ticket_id}' not found in active database.")
        _save_tickets(tickets)
        result_meta["ticket_id"] = ticket_id
        result_meta["status_updated_to"] = "resolved"
        log.info("ticket_handler.auto_respond_success", ticket_id=ticket_id)
    else:
        log.info("ticket_handler.general_auto_respond_success")

    return result_meta


def execute_escalate(ticket_id: str, reason: str, evidence: str) -> dict[str, Any]:
    """Escalate a ticket to senior security staff, citing evidence."""
    if not ticket_id or not ticket_id.strip():
        raise ActionExecutionError("ticket_id is required.")
    if not reason or not reason.strip():
        raise ActionExecutionError("escalation reason is required.")
    if not evidence or not evidence.strip():
        raise ActionExecutionError("evidence justifying escalation must be provided.")

    tickets = _load_tickets()
    ticket_id_norm = ticket_id.strip().upper()
    found = False
    updated_ticket = None

    for ticket in tickets:
        if str(ticket.get("id", "")).strip().upper() == ticket_id_norm:
            ticket["status"] = "escalated"
            ticket["escalation_reason"] = reason
            ticket["evidence_cited"] = evidence
            # Escalate priority to High or Critical if not already
            if ticket.get("priority", "medium") not in ("high", "critical"):
                ticket["priority"] = "high"
            found = True
            updated_ticket = ticket
            break

    if not found:
        raise ActionExecutionError(f"Ticket '{ticket_id}' not found in active database.")

    _save_tickets(tickets)
    log.info("ticket_handler.escalate_success", ticket_id=ticket_id)
    return {
        "ticket_id": ticket_id,
        "status_updated_to": "escalated",
        "priority": updated_ticket.get("priority"),
        "reason": reason,
        "evidence_cited": evidence,
        "success": True
    }


def execute_request_info(ticket_id: str, info_requested: str, evidence: str) -> dict[str, Any]:
    """Request more information from client, citing evidence of missing details."""
    if not ticket_id or not ticket_id.strip():
        raise ActionExecutionError("ticket_id is required.")
    if not info_requested or not info_requested.strip():
        raise ActionExecutionError("info_requested details are required.")
    if not evidence or not evidence.strip():
        raise ActionExecutionError("evidence justifying request must be provided.")

    tickets = _load_tickets()
    ticket_id_norm = ticket_id.strip().upper()
    found = False

    for ticket in tickets:
        if str(ticket.get("id", "")).strip().upper() == ticket_id_norm:
            ticket["status"] = "pending"
            ticket["info_requested"] = info_requested
            ticket["evidence_cited"] = evidence
            found = True
            break

    if not found:
        raise ActionExecutionError(f"Ticket '{ticket_id}' not found in active database.")

    _save_tickets(tickets)
    log.info("ticket_handler.request_info_success", ticket_id=ticket_id)
    return {
        "ticket_id": ticket_id,
        "status_updated_to": "pending",
        "info_requested": info_requested,
        "evidence_cited": evidence,
        "success": True
    }


def execute_close(ticket_id: str, reason: str, evidence: str) -> dict[str, Any]:
    """Close a ticket permanently, citing resolution verification evidence."""
    if not ticket_id or not ticket_id.strip():
        raise ActionExecutionError("ticket_id is required.")
    if not reason or not reason.strip():
        raise ActionExecutionError("closure reason is required.")
    if not evidence or not evidence.strip():
        raise ActionExecutionError("evidence justifying closure must be provided.")

    tickets = _load_tickets()
    ticket_id_norm = ticket_id.strip().upper()
    found = False

    for ticket in tickets:
        if str(ticket.get("id", "")).strip().upper() == ticket_id_norm:
            ticket["status"] = "closed"
            ticket["closure_reason"] = reason
            ticket["evidence_cited"] = evidence
            found = True
            break

    if not found:
        raise ActionExecutionError(f"Ticket '{ticket_id}' not found in active database.")

    _save_tickets(tickets)
    log.info("ticket_handler.close_success", ticket_id=ticket_id)
    return {
        "ticket_id": ticket_id,
        "status_updated_to": "closed",
        "closure_reason": reason,
        "evidence_cited": evidence,
        "success": True
    }

"""
Unit tests for the read handler.
Uses tmp_path with seeded JSON data — no dependency on real data/knowledge/tickets/.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.action.handlers.read_handler import read_ticket, read_ticket_list
from shared.exceptions import ActionExecutionError

_SAMPLE_TICKETS = [
    {"id": "TK-001", "title": "VPN issue",    "status": "open",     "priority": "high",   "category": "network"},
    {"id": "TK-002", "title": "Email broken",  "status": "resolved", "priority": "medium", "category": "email"},
    {"id": "TK-003", "title": "Printer down",  "status": "open",     "priority": "low",    "category": "hardware"},
]


@pytest.fixture(autouse=True)
def patch_tickets_dir(tmp_path: Path):
    """Write sample tickets to a temp dir and patch _TICKETS_DIR."""
    tickets_file = tmp_path / "tickets.json"
    tickets_file.write_text(json.dumps(_SAMPLE_TICKETS))
    with patch("services.action.handlers.read_handler._TICKETS_DIR", tmp_path):
        yield


class TestReadTicket:
    def test_returns_ticket_by_id(self) -> None:
        ticket = read_ticket("TK-001")
        assert ticket["id"] == "TK-001"
        assert ticket["title"] == "VPN issue"

    def test_case_insensitive_id_lookup(self) -> None:
        ticket = read_ticket("tk-001")
        assert ticket["id"] == "TK-001"

    def test_raises_on_not_found(self) -> None:
        with pytest.raises(ActionExecutionError):
            read_ticket("TK-999")

    def test_raises_on_empty_id(self) -> None:
        with pytest.raises(ActionExecutionError):
            read_ticket("")


class TestReadTicketList:
    def test_returns_all_by_default(self) -> None:
        results = read_ticket_list()
        assert len(results) == 3

    def test_filters_by_status(self) -> None:
        open_tickets = read_ticket_list(status="open")
        assert all(t["status"] == "open" for t in open_tickets)
        assert len(open_tickets) == 2

    def test_filters_by_priority(self) -> None:
        high_tickets = read_ticket_list(priority="high")
        assert len(high_tickets) == 1
        assert high_tickets[0]["id"] == "TK-001"

    def test_filters_by_category(self) -> None:
        email_tickets = read_ticket_list(category="email")
        assert len(email_tickets) == 1

    def test_limit_is_applied(self) -> None:
        results = read_ticket_list(limit=1)
        assert len(results) == 1

    def test_limit_clamped_to_100(self) -> None:
        results = read_ticket_list(limit=9999)
        assert len(results) <= 100

    def test_no_match_returns_empty(self) -> None:
        results = read_ticket_list(status="nonexistent")
        assert results == []

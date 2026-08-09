"""
Unit tests for the new ticket triage handlers.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.action.handlers.ticket_handler import (
    execute_auto_respond,
    execute_close,
    execute_escalate,
    execute_request_info,
)
from shared.exceptions import ActionExecutionError

_SAMPLE_TICKETS = [
    {
        "id": "TK-001",
        "title": "Critical RCE",
        "status": "open",
        "priority": "critical",
        "category": "pentest",
        "description": "RCE on upload page.",
    },
    {
        "id": "TK-002",
        "title": "SOC 2 Audit",
        "status": "open",
        "priority": "medium",
        "category": "compliance",
        "description": "SOC 2 readiness.",
    },
]


@pytest.fixture(autouse=True)
def patch_workspace(tmp_path: Path):
    """Redirect WORKSPACE_ROOT and _TICKETS_FILE to temp path."""
    fake_workspace = tmp_path
    tickets_file = fake_workspace / "tickets.json"
    tickets_file.write_text(json.dumps(_SAMPLE_TICKETS))
    with (
        patch("services.action.handlers.ticket_handler.WORKSPACE_ROOT", fake_workspace),
        patch("services.action.handlers.ticket_handler._TICKETS_FILE", tickets_file),
    ):
        yield fake_workspace


class TestTicketHandlers:
    def test_auto_respond_updates_ticket(self, patch_workspace: Path) -> None:
        res = execute_auto_respond("TK-001", "This is an auto response.", "FAQ Section 2")
        assert res["status_updated_to"] == "resolved"
        assert res["ticket_id"] == "TK-001"

        # Check saved data
        saved = json.loads((patch_workspace / "tickets.json").read_text())
        assert saved[0]["status"] == "resolved"
        assert saved[0]["resolution_response"] == "This is an auto response."
        assert saved[0]["evidence_cited"] == "FAQ Section 2"

    def test_auto_respond_general_no_ticket(self) -> None:
        res = execute_auto_respond(None, "General info answer", "FAQ Section 1")
        assert res["response"] == "General info answer"
        assert "ticket_id" not in res

    def test_escalate_updates_ticket(self, patch_workspace: Path) -> None:
        res = execute_escalate("TK-002", "Requires Tier 2 review", "SLA policy rule SLA-002")
        assert res["status_updated_to"] == "escalated"
        assert res["priority"] == "high"

        # Check saved data
        saved = json.loads((patch_workspace / "tickets.json").read_text())
        assert saved[1]["status"] == "escalated"
        assert saved[1]["priority"] == "high"
        assert saved[1]["escalation_reason"] == "Requires Tier 2 review"
        assert saved[1]["evidence_cited"] == "SLA policy rule SLA-002"

    def test_request_info_updates_ticket(self, patch_workspace: Path) -> None:
        res = execute_request_info("TK-002", "Please send VPN credentials", "RoE scoping section")
        assert res["status_updated_to"] == "pending"

        # Check saved data
        saved = json.loads((patch_workspace / "tickets.json").read_text())
        assert saved[1]["status"] == "pending"
        assert saved[1]["info_requested"] == "Please send VPN credentials"
        assert saved[1]["evidence_cited"] == "RoE scoping section"

    def test_close_updates_ticket(self, patch_workspace: Path) -> None:
        res = execute_close("TK-001", "Client confirmed mitigation", "Retesting policy section")
        assert res["status_updated_to"] == "closed"

        # Check saved data
        saved = json.loads((patch_workspace / "tickets.json").read_text())
        assert saved[0]["status"] == "closed"
        assert saved[0]["closure_reason"] == "Client confirmed mitigation"
        assert saved[0]["evidence_cited"] == "Retesting policy section"

    def test_invalid_ticket_raises_error(self) -> None:
        with pytest.raises(ActionExecutionError):
            execute_escalate("TK-999", "reason", "evidence")

    def test_postgres_fallback_when_unconfigured(self) -> None:
        from services.action.handlers.ticket_handler import get_pg_pool

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("services.action.handlers.ticket_handler._pg_pool", None),
        ):
            pool = get_pg_pool()
            assert pool is None

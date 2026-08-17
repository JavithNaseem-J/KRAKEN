from __future__ import annotations

from unittest.mock import patch

from src.tools.ticket import execute_create_ticket


def test_editable_hitl_ticket_fields(tmp_path) -> None:
    tickets_file = tmp_path / "tickets.json"
    tickets_file.write_text("[]", encoding="utf-8")
    with (
        patch("src.tools.ticket.WORKSPACE_ROOT", tmp_path),
        patch("src.tools.ticket._TICKETS_FILE", tickets_file),
    ):
        res = execute_create_ticket(
            user_name="Alice",
            category="Hardware",
            priority="High",
            description="Broken monitor malfunction",
        )
        assert res.get("success") is True

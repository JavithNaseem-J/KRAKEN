from __future__ import annotations

import pytest
from services.action.handlers.ticket_handler import execute_create_ticket


def test_editable_hitl_ticket_fields() -> None:
    res = execute_create_ticket(
        user_name="Alice",
        category="Hardware",
        priority="High",
        description="Broken monitor malfunction",
    )

    assert isinstance(res, dict)
    assert "ticket_id" in res
    assert res["user"] == "Alice"
    assert res["category"] == "Hardware"
    assert res["priority"] == "high"
    assert res["description"] == "Broken monitor malfunction"

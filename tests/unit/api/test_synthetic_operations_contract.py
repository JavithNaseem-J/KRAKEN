from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from src.api.action import _dispatch_synthetic
from src.utils.config import Settings
from src.utils.exceptions import ActionExecutionError
from src.utils.models.action import RiskLevel
from src.utils.registry import REGISTRY
from src.utils.synthetic_tickets import SyntheticTicketRepository


def repository(write_limit: int = 5) -> SyntheticTicketRepository:
    return SyntheticTicketRepository(
        Settings(
            environment="test",
            hitl_service_token="test-hitl-token-0123456789abcdef0123456789",
            public_write_limit=write_limit,
        )
    )


def test_create_ticket_is_immediate_safe_and_session_private() -> None:
    repo = repository()
    result = _dispatch_synthetic(
        "create_ticket",
        {
            "user_name": "Morgan Reed",
            "category": "VPN",
            "priority": "medium",
            "description": "VPN disconnects after sign-in",
        },
        "session-a",
        repo,
    )

    assert REGISTRY["create_ticket"].risk_level == RiskLevel.SAFE
    assert REGISTRY["create_ticket"].requires_hitl is False
    assert result["ticket_id"].startswith("SYN-")
    assert result["synthetic"] is True
    assert repo.get("session-a", result["ticket_id"])["status"] == "open"
    with pytest.raises(ActionExecutionError, match="not found"):
        repo.get("session-b", result["ticket_id"])


def test_seed_mutation_is_an_isolated_overlay() -> None:
    repo = repository()
    repo.mutate("session-a", "TCK-24001", status="closed")

    assert repo.get("session-a", "TCK-24001")["status"] == "closed"
    assert repo.get("session-b", "TCK-24001")["status"] == "OPEN"


def test_public_environment_rejects_filesystem_actions_and_sixth_write() -> None:
    repo = repository(write_limit=5)
    with pytest.raises(ActionExecutionError, match="Filesystem"):
        _dispatch_synthetic("write_json_file", {"target_path": "x.json", "content": {}}, "s", repo)

    for _ in range(5):
        repo.create(
            "s",
            {
                "user_name": "Morgan",
                "category": "IT",
                "priority": "low",
                "description": "Synthetic request",
            },
        )
    with pytest.raises(ActionExecutionError, match="write limit"):
        repo.create(
            "s",
            {
                "user_name": "Morgan",
                "category": "IT",
                "priority": "low",
                "description": "Sixth request",
            },
        )


def test_concurrent_sessions_cannot_read_each_others_created_tickets() -> None:
    repo = repository()

    def create_for(session_id: str) -> dict[str, object]:
        return repo.create(
            session_id,
            {
                "user_name": session_id,
                "category": "IT",
                "priority": "medium",
                "description": f"Private request for {session_id}",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        ticket_a, ticket_b = executor.map(create_for, ("session-a", "session-b"))

    assert ticket_a["ticket_id"] != ticket_b["ticket_id"]
    with pytest.raises(ActionExecutionError, match="not found"):
        repo.get("session-a", str(ticket_b["ticket_id"]))
    with pytest.raises(ActionExecutionError, match="not found"):
        repo.get("session-b", str(ticket_a["ticket_id"]))


def test_expired_synthetic_ticket_scope_is_cleaned_up() -> None:
    now = [1000.0]
    settings = Settings(
        environment="test",
        hitl_service_token="test-hitl-token-0123456789abcdef0123456789",
        public_session_ttl_seconds=60,
    )
    repo = SyntheticTicketRepository(settings, clock=lambda: now[0])
    repo.create(
        "expired-session",
        {
            "user_name": "Morgan",
            "category": "IT",
            "priority": "low",
            "description": "Temporary request",
        },
    )

    now[0] += 61
    repo.cleanup()

    assert "expired-session" not in repo._sessions

from __future__ import annotations

from src.api.report import generate_incident_html


def test_html_generation() -> None:
    session_data = {
        "session_id": "test-session-1234-5678-90ab",
        "persona": {"label": "Alice", "title": "Tier 1 Analyst"},
        "messages": [
            {
                "role": "user",
                "content": "Create IT ticket for laptop issue",
                "timestamp": "2026-08-14T18:00:00Z",
            },
            {
                "role": "assistant",
                "content": "Creating IT ticket TCK-1001 for Alice's laptop issue.",
                "timestamp": "2026-08-14T18:00:02Z",
            },
        ],
    }

    html = generate_incident_html(session_data)
    assert isinstance(html, str)
    assert len(html) > 0
    assert "<!DOCTYPE html>" in html
    assert "test-session-1234-5678-90ab" in html
    assert "Alice" in html
    assert "Create IT ticket for laptop issue" in html

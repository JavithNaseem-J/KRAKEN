from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.gateway import app
from src.api.report import generate_incident_html


def _session_data() -> dict:
    return {
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


def test_html_generation() -> None:
    html = generate_incident_html(_session_data())

    assert isinstance(html, str)
    assert len(html) > 0
    assert "<!DOCTYPE html>" in html
    assert "test-session-1234-5678-90ab" in html
    assert "Alice" in html
    assert "Create IT ticket for laptop issue" in html


def test_report_export_returns_html_media_contract() -> None:
    client = TestClient(app)
    try:
        response = client.post(
            "/v1/report/export",
            json=_session_data(),
            headers={"X-API-Key": "dev-key-analyst-default"},
        )
    finally:
        client.close()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'filename="kraken-incident-test-ses.html"' in response.headers["content-disposition"]

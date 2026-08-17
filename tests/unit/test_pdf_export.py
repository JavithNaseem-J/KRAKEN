from __future__ import annotations

from src.api.report import generate_incident_pdf


def test_pdf_generation() -> None:
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

    pdf_bytes = generate_incident_pdf(session_data)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")

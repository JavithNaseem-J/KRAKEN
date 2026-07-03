"""Seed script — populates dev/test data."""
from __future__ import annotations

import json
from pathlib import Path

TICKETS_DIR = Path(__file__).parent.parent / "data" / "knowledge" / "tickets"
WORKSPACE_DIR = Path(__file__).parent.parent / "data" / "workspace"

SAMPLE_TICKETS = [
    {"id": "TK-001", "title": "VPN not connecting", "status": "open",
     "priority": "high", "category": "network", "description": "User cannot connect to VPN from home."},
    {"id": "TK-002", "title": "Outlook sync issue", "status": "resolved",
     "priority": "medium", "category": "email", "description": "Outlook calendar not syncing with mobile."},
    {"id": "TK-003", "title": "Printer offline", "status": "open",
     "priority": "low", "category": "hardware", "description": "Floor 3 printer showing offline status."},
]


def main() -> None:
    TICKETS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    out = TICKETS_DIR / "sample_tickets.json"
    out.write_text(json.dumps(SAMPLE_TICKETS, indent=2))
    print(f"Seeded {len(SAMPLE_TICKETS)} tickets → {out}")
    print("Seed complete.")


if __name__ == "__main__":
    main()

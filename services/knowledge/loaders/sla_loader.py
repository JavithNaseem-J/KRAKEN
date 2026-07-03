"""
SLA / Escalation rules loader.

Reads .json files from data/knowledge/sla/.
Expected schema per rule:
  {
    "id": "SLA-001",
    "name": "High Priority Ticket SLA",
    "priority": "high",
    "response_time_hours": 4,
    "resolution_time_hours": 8,
    "escalation_path": ["L1 Support", "L2 Support", "Manager"],
    "notes": "Optional free text"
  }

Each rule is converted to a human-readable text chunk for semantic search.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

SLA_DIR = Path(__file__).resolve().parents[4] / "data" / "knowledge" / "sla"


def _rule_to_text(rule: dict[str, Any]) -> str:
    """Convert an SLA rule dict to a natural-language text chunk."""
    escalation = " → ".join(rule.get("escalation_path", []))
    parts = [
        f"SLA Rule: {rule.get('name', rule.get('id', 'unknown'))}",
        f"Priority level: {rule.get('priority', '')}",
        f"Response time: {rule.get('response_time_hours', '?')} hours",
        f"Resolution time: {rule.get('resolution_time_hours', '?')} hours",
        f"Escalation path: {escalation}" if escalation else "",
        f"Notes: {rule.get('notes', '')}" if rule.get("notes") else "",
    ]
    return "\n".join(p for p in parts if p)


def load_sla_chunks() -> list[dict[str, Any]]:
    """
    Load all SLA rule files and return ChromaDB-ready chunk dicts.

    Returns:
        List of dicts with keys: id, document, metadata
    """
    if not SLA_DIR.exists():
        log.warning("sla_loader.dir_missing", path=str(SLA_DIR))
        return []

    files = [f for f in SLA_DIR.iterdir() if f.suffix.lower() == ".json"]

    if not files:
        log.warning("sla_loader.no_files", path=str(SLA_DIR))
        return []

    all_chunks: list[dict[str, Any]] = []

    for file_path in sorted(files):
        log.info("sla_loader.loading", file=file_path.name)
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.error("sla_loader.parse_error", file=file_path.name, error=str(exc))
            continue

        rules = data if isinstance(data, list) else [data]

        for rule in rules:
            rule_id = str(rule.get("id", ""))
            if not rule_id:
                log.warning("sla_loader.missing_id", rule=rule)
                continue

            all_chunks.append({
                "id":       f"sla_{rule_id}",
                "document": _rule_to_text(rule),
                "metadata": {
                    "source":                  "sla",
                    "rule_id":                 rule_id,
                    "priority":                str(rule.get("priority", "")),
                    "response_time_hours":     str(rule.get("response_time_hours", "")),
                    "resolution_time_hours":   str(rule.get("resolution_time_hours", "")),
                },
            })

        log.info("sla_loader.done", file=file_path.name, rules=len(rules))

    log.info("sla_loader.complete", total_chunks=len(all_chunks))
    return all_chunks

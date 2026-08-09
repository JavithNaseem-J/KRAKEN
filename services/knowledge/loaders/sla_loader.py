"""
SLA / Escalation rules loader.
Reads .json files from data/knowledge/sla/.
Converts rules into human-readable text chunks for semantic search.
"""

from __future__ import annotations

from typing import Any

from .base import load_structured_chunks, resolve_data_dir

from shared.models.knowledge import SLADocument

SLA_DIR = resolve_data_dir("sla")


def _rule_to_text(rule_raw: dict[str, Any]) -> str:
    """Convert an SLA rule dict to a natural-language text chunk via SLADocument validation."""
    rule_id = rule_raw.get("rule_id") or rule_raw.get("id") or "sla_unknown"
    severity = rule_raw.get("severity") or rule_raw.get("priority") or "medium"
    resp_mins = rule_raw.get("response_sla_minutes") or (rule_raw.get("response_time_hours", 1) * 60)
    res_mins = rule_raw.get("resolution_sla_minutes") or (rule_raw.get("resolution_time_hours", 4) * 60)

    sla_doc = SLADocument(
        rule_id=str(rule_id),
        severity=str(severity),
        response_sla_minutes=int(resp_mins),
        resolution_sla_minutes=int(res_mins),
        description=str(rule_raw.get("notes") or rule_raw.get("name") or "SLA Policy Rule"),
    )

    escalation = " → ".join(rule_raw.get("escalation_path", []))
    parts = [
        f"SLA Rule: {sla_doc.rule_id}",
        f"Severity level: {sla_doc.severity}",
        f"Response time: {sla_doc.response_sla_minutes} minutes",
        f"Resolution time: {sla_doc.resolution_sla_minutes} minutes",
        f"Escalation path: {escalation}" if escalation else "",
        f"Description: {sla_doc.description}",
    ]
    return "\n".join(p for p in parts if p)


def load_sla_chunks() -> list[dict[str, Any]]:
    """Load all SLA rules from JSON files."""
    return load_structured_chunks(
        data_dir=SLA_DIR,
        allowed_suffixes={".json"},
        record_to_text=_rule_to_text,
        id_prefix="sla",
    )

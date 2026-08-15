"""
SLA / Escalation rules loader.
Reads .json files from data/knowledge/sla/.
Converts severities (P1-P4) and action_risk_mapping into text chunks for semantic search.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from .base import resolve_data_dir

log = structlog.get_logger(__name__)
SLA_DIR = resolve_data_dir("sla")


def load_sla_chunks() -> list[dict[str, Any]]:
    """
    Load SLA rules from data/knowledge/sla/sla_rules.json.
    Iterates severities (P1-P4) and action_risk_mapping, returning structured text chunks.
    """
    chunks: list[dict[str, Any]] = []
    if not SLA_DIR.exists():
        return chunks

    for json_path in sorted(SLA_DIR.glob("*.json")):
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            log.warning("sla_loader.json_load_failed", path=str(json_path), error=str(exc))
            continue

        if not isinstance(data, dict):
            continue

        severities = data.get("severities", {})
        if isinstance(severities, dict):
            for p_level, p_info in severities.items():
                if not isinstance(p_info, dict):
                    continue
                name = p_info.get("name", "")
                desc = p_info.get("description", "")
                resp_mins = p_info.get("response_time_minutes")
                res_hours = p_info.get("resolution_time_hours")
                app_level = p_info.get("approval_level", "")
                escalation = p_info.get("escalation_chain", [])
                esc_str = " → ".join(escalation) if isinstance(escalation, list) else str(escalation)

                content_parts = [
                    f"SLA Severity Level: {p_level} ({name})",
                    f"Description: {desc}",
                    f"Response SLA: {resp_mins} minutes" if resp_mins is not None else "",
                    f"Resolution SLA: {res_hours} hours" if res_hours is not None else "",
                    f"Required Approval Level: {app_level}" if app_level else "",
                    f"Escalation Chain: {esc_str}" if esc_str else "",
                ]
                content = "\n".join(p for p in content_parts if p)

                chunks.append({
                    "chunk_id": f"sla_{p_level.lower()}",
                    "content": content,
                    "metadata": {
                        "severity": p_level,
                        "name": name,
                        "response_time_minutes": resp_mins,
                        "resolution_time_hours": res_hours,
                        "file_name": json_path.name,
                    },
                })

        risk_mapping = data.get("action_risk_mapping", {})
        if isinstance(risk_mapping, dict) and risk_mapping:
            mapping_lines = [f"- {action}: {risk}" for action, risk in risk_mapping.items()]
            content = "SLA Action Risk Level Mapping:\n" + "\n".join(mapping_lines)
            chunks.append({
                "chunk_id": "sla_action_risk_mapping",
                "content": content,
                "metadata": {
                    "type": "action_risk_mapping",
                    "file_name": json_path.name,
                },
            })

    return chunks

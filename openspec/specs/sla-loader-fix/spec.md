# sla-loader-fix Specification

## Purpose
TBD - created by archiving change codebase-health-remediation. Update Purpose after archive.
## Requirements
### Requirement: SLA loader iterates the actual nested JSON structure
The SLA loader in `services/knowledge/loaders/sla_loader.py` SHALL iterate the `severities` mapping (keys `P1` through `P4`) and `action_risk_mapping` from the actual `sla_rules.json` data shape, producing one text chunk per severity level and one chunk for the risk mapping.

#### Scenario: Loading sla_rules.json produces per-severity chunks
- **WHEN** `load_sla_chunks()` processes `data/knowledge/sla/sla_rules.json`
- **THEN** at least 4 chunks are produced (one per P1, P2, P3, P4), each containing the severity name, description, response time, resolution time, approval level, and escalation chain

#### Scenario: Action risk mapping is indexed
- **WHEN** `load_sla_chunks()` processes the `action_risk_mapping` section
- **THEN** a chunk is produced listing each action and its risk classification (e.g., "auto_respond: SAFE", "write_json_file: CRITICAL")

#### Scenario: No garbage "sla_unknown" chunks
- **WHEN** `load_sla_chunks()` completes
- **THEN** no chunk contains `rule_id: sla_unknown` or `severity: medium` as fallback values from failed field extraction


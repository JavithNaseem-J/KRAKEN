# shared-audit-client Specification

## Purpose
TBD - created by archiving change codebase-health-remediation. Update Purpose after archive.
## Requirements
### Requirement: audit_client is a shared module importable by all services
`shared/audit_client.py` SHALL contain the `fire_audit_log()` function. All services (including orchestrator and action) SHALL import it from `shared.audit_client`. The file `services/action/audit_client.py` SHALL NOT exist.

#### Scenario: Orchestrator fires audit log in Docker
- **WHEN** the orchestrator service runs in its own Docker container and calls `fire_audit_log()`
- **THEN** the import succeeds because `shared/audit_client.py` is available via the shared package (not a cross-service import)

#### Scenario: Action service fires audit log
- **WHEN** the action service calls `fire_audit_log()` from `shared.audit_client`
- **THEN** the audit log is sent to the audit service without import errors


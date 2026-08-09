## ADDED Requirements

### Requirement: Shared AuditLogRequest model
A shared `AuditLogRequest` Pydantic model SHALL exist in `shared/models/audit.py` and be the single source of truth for the audit-log entry schema. No service SHALL define its own local copy of this model.

#### Scenario: Audit service uses shared model
- **WHEN** the audit service receives a POST /log request
- **THEN** it SHALL validate the body against `shared.models.audit.AuditLogRequest` (not a locally-defined model)

#### Scenario: Producers construct typed model
- **WHEN** `action/audit_client.py` fires an audit entry
- **THEN** it SHALL construct a `shared.models.audit.AuditLogRequest` instance and call `.model_dump()` to produce the JSON body, rather than assembling a raw dict

#### Scenario: AuditStore accepts shared model
- **WHEN** `audit_store.AuditStore.log_action` is called
- **THEN** it SHALL accept an `AuditLogRequest` instance directly (not 11 keyword arguments) and extract fields from it internally

#### Scenario: Field rename propagates atomically
- **WHEN** a field in `AuditLogRequest` is renamed
- **THEN** mypy SHALL report type errors at all producers and the store simultaneously, preventing silent misalignment

## Why

Following a technical audit across all microservices, critical structural debt and security guardrail gaps were identified: missing prompt injection and PII sanitization in the gateway, lack of SHA-256 cryptographic hash chaining in the audit log, duplicate agent state definitions, and unstandardized action error handling.

Remediating these findings hardens the gateway against prompt injection / PII leakage, guarantees tamper-evident audit logs via SHA-256 Merkle chaining, consolidates duplicated models/scripts, and cleans up dead files.

## What Changes

- **Input Security & Guardrails**:
  - Add prompt injection pattern scanning and basic PII masking middleware (`PromptGuardMiddleware`) to `services/gateway/middleware/`.
- **Cryptographic Audit Log Chaining**:
  - Add SHA-256 `previous_hash` cryptographic chaining to `audit_log` in `services/audit/audit_store.py` and `scripts/init.sql`.
- **State Schema Consolidation**:
  - Unify `AgentState` in `services/orchestrator/graph/state.py` to derive directly from Pydantic models in `shared/models/agent.py`.
- **Structural Cleanup & Error Standardization**:
  - Refactor `scripts/ingest_knowledge.py` to reuse `services.knowledge.ingest.run_ingest_async()`.
  - Refactor `services/gateway/middleware/auth.py` to reuse `shared/auth.py` helpers.
  - Update `services/action/audit_client.py` to use `AuditLogEntry.model_dump()`.
  - Standardize error handling in `services/action/handlers/ticket_handler.py` to raise `ActionExecutionError`.
  - Delete stale `ARCHITECTURE.md` and unreferenced `scripts/migrate_to_supabase.py`.

## Capabilities

### New Capabilities
- `gateway-input-guardrails`: Prompt injection detection and PII sanitization in the edge gateway.

### Modified Capabilities
- `audit-contract`: SHA-256 cryptographic hash chaining for tamper-evident audit logs.
- `action-dispatch`: Standardized error raising with `ActionExecutionError` across all handlers.

## Impact

- **Services**: `services/gateway/`, `services/audit/`, `services/orchestrator/`, `services/action/`, `shared/`
- **Database**: `scripts/init.sql` (`audit_log` table schema updated with `previous_hash`)
- **Documentation & Scripts**: Cleanup of stale `ARCHITECTURE.md` and unused migration scripts.

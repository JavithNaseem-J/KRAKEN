## 1. Gateway Prompt Guard & Input Security

- [x] 1.1 Implement `PromptGuardMiddleware` in `services/gateway/middleware/prompt_guard.py` for prompt injection scanning and PII masking
- [x] 1.2 Mount `PromptGuardMiddleware` in `services/gateway/main.py`
- [x] 1.3 Refactor `services/gateway/middleware/auth.py` to reuse token validation helpers from `shared/auth.py`

## 2. Cryptographic Audit Log Chaining

- [x] 2.1 Update `scripts/init.sql` to add `previous_hash VARCHAR(64)` column and index to `audit_log`
- [x] 2.2 Implement SHA-256 hash chaining calculation in `services/audit/audit_store.py` (`AuditStore.log_action`)
- [x] 2.3 Update `services/action/audit_client.py` to serialize `AuditLogEntry.model_dump()`

## 3. Schema & Handler Consolidation

- [x] 3.1 Unify `AgentState` in `services/orchestrator/graph/state.py` to import directly from `shared.models.agent`
- [x] 3.2 Standardize error handling in `services/action/handlers/ticket_handler.py` to raise `ActionExecutionError`
- [x] 3.3 Refactor `scripts/ingest_knowledge.py` to reuse `services.knowledge.ingest.run_ingest_async()`

## 4. Dead Code Cleanup & Verification

- [x] 4.1 Delete stale root `ARCHITECTURE.md` and unreferenced `scripts/migrate_to_supabase.py`
- [x] 4.2 Add unit tests for `PromptGuardMiddleware` and SHA-256 audit chaining
- [x] 4.3 Run `uv run pytest tests/unit/ -v` to verify 100% test pass rate

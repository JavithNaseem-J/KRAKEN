## Context

The system-wide audit revealed key security and structural gaps across the microservices:
1. **Input Security**: The gateway proxies raw user messages directly to orchestrator without prompt injection or PII checks.
2. **Audit Integrity**: Audit log entries are written as independent rows; if a PostgreSQL DB administrator alters or deletes rows, the tampering is undetectable.
3. **State Schema Drift**: `AgentState` is defined as both a Pydantic model in `shared/models/agent.py` and a TypedDict in `orchestrator/graph/state.py`.
4. **Action Handlers Exception Handling**: `ticket_handler.py` catches errors and returns dictionaries with `"error"` keys, creating inconsistent error paths compared to `write_handler.py` (which raises `ActionExecutionError`).

## Goals / Non-Goals

**Goals:**
- Implement `PromptGuardMiddleware` in `services/gateway/middleware/prompt_guard.py` to block prompt injection patterns (system prompt overrides, jailbreaks) and mask PII (SSN, credit card patterns).
- Implement SHA-256 cryptographic hash chaining in `services/audit/audit_store.py` (`previous_hash` column) to make `audit_log` tamper-evident.
- Consolidate `AgentState` in `services/orchestrator/graph/state.py` to derive from `shared/models/agent.py`.
- Standardize all action handlers to raise `ActionExecutionError` consistently.
- Remove redundant scripts (`migrate_to_supabase.py`), obsolete documentation (`ARCHITECTURE.md`), and duplicate ingestion logic.

**Non-Goals:**
- Replacing PostgreSQL or Redis persistence layers.
- Changing the LangGraph node graph topology or routing rules.

## Decisions

### Decision 1: Edge Gateway Prompt Guard Middleware
Implement lightweight regex-based pattern matching in `services/gateway/middleware/prompt_guard.py` for system prompt overrides, delimiter injection (`<|im_start|>`, `[INST]`), and PII patterns (SSNs, credit card numbers). Rejections return HTTP 400 Bad Request before hitting downstream services.

### Decision 2: SHA-256 Hash Chaining for Audit Log
Add `previous_hash VARCHAR(64)` to `audit_log` table. When storing an audit entry, calculate `current_hash = SHA256(previous_hash + timestamp + action_name + session_id + payload_json)`. If the table is empty, `previous_hash` defaults to `0000000000000000000000000000000000000000000000000000000000000000`.

### Decision 3: Pydantic-First Agent State Definition
Update `services/orchestrator/graph/state.py` to import `AgentState` from `shared.models.agent` (or use `TypedDict` derived from `AgentState` fields) ensuring a single canonical definition across the repository.

### Decision 4: Fail-Fast Action Execution Exceptions
Refactor `execute_auto_respond`, `execute_escalate`, `execute_request_info`, and `execute_close` in `services/action/handlers/ticket_handler.py` to raise `ActionExecutionError` on failure rather than returning `{"status": "failure", "error": "..."}` dicts.

## Risks / Trade-offs

- **[Risk]** False positive prompt injection blocks valid IT support queries.  
  → *Mitigation:* Limit regex rules to unambiguous prompt override idioms (`ignore previous instructions`, `system prompt:`) and log blocked queries at warning level.
- **[Risk]** Hash chain computation overhead on audit log writes.  
  → *Mitigation:* SHA-256 computation over small string payloads takes <1ms in Python.

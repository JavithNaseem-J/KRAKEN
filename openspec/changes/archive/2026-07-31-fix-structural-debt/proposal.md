## Why

The full-repo audit (`REPORT1_STRUCTURAL_DEBT.md`) identified 28 structural debt issues across 12 folders — including 3 active runtime crashes that break the system right now, 6 instances of duplicated logic, 8 dead-code items, and 3 pattern inconsistencies. These are not theoretical risks: the action service fails at import, ticket ingestion silently skips all ticket data, and multi-turn conversation history is never loaded. Fixing these now, before any feature work, establishes a clean and reliable foundation.

## What Changes

- **Fix `Callable` NameError in `services/action/main.py`**: The action service module fails to import, crashing all action executions with HTTP 500 before any handler runs.
- **Fix `settings.memory_service_url` AttributeError in `services/orchestrator/main.py`**: Every `/run` call silently discards session history; multi-turn dialogue is broken for all users.
- **Fix tuple-unpack crash in `scripts/ingest_knowledge.py`**: Ticket data is never loaded into ChromaDB; the agent always operates with zero ticket-history knowledge.
- **Consolidate HTTP client construction**: The `httpx.AsyncClient` timeout tuple and `X-Service-Token` header dict are duplicated across `gateway`, `approval`, and `action/orchestrator` — replace with shared factory calls.
- **Eliminate double JSON serialisation in `write_handler.py`**: The same JSON bytes are produced twice per write; de-duplicate by returning byte count from `atomic_write_json`.
- **Extract `_find_ticket()` helper**: The O(n) scan + "not found → raise" block is copy-pasted in all four ticket handler functions; extract to a single helper.
- **Fix ingest script duplication**: The ingestion pipeline exists in both `scripts/ingest_knowledge.py` and `services/knowledge/main.py`'s `_run_ingest()`; extract shared loader logic.
- **Move in-function imports to module level in `retriever.py`**: `import json` and `import uuid` are inside the `retrieve()` function body; move them to the top.
- **Remove 8 unused imports** (`secrets`, `Header`, `os`, `tempfile` where redundant) from `approval/main.py`, `audit/main.py`, `memory/main.py`, `knowledge/main.py`, `orchestrator/main.py`.
- **Fix shadow-meta key docstring mismatch in `approval/queue.py`**: The docstring describes a never-implemented design; correct it.
- **Fix approval URL hardcoding in `frontend/app.py`**: The approval link is hardcoded to `localhost:8004` in two places; read from `APPROVAL_URL` env var instead.
- **Fix `get_settings()` call placement in `audit_client.py`**: Called inside async function body on every invocation; move to module level to match repo-wide pattern.
- **Fix `_INDEX` TTL in `approval/queue.py`**: The Redis index TTL slides forward with every enqueue instead of using a fixed `timeout + buffer`.
- **Standardise per-service `requirements.txt` duplication**: Shared deps appear in up to 8 files; document the split or consolidate.
- **Remove empty `docs/` directory or populate it**: It is an empty dead artifact.

## Capabilities

### New Capabilities

- `shared-http-client-factory`: Centralised `create_async_http_client()` and `service_headers()` helpers used by all services — eliminates all inline `httpx.Timeout` and `X-Service-Token` constructions.
- `shared-ticket-lookup`: `_find_ticket(tickets, ticket_id)` helper in `ticket_handler.py` — eliminates the four copy-pasted linear-scan blocks.

### Modified Capabilities

*(No spec-level behaviour changes — all fixes are implementation-layer corrections to existing capabilities.)*

## Impact

- **`services/action/main.py`**: Import fix — zero behaviour change, restores service boot.
- **`services/orchestrator/main.py`**: `memory_url` rename fix — restores session history loading on every `/run` call.
- **`scripts/ingest_knowledge.py`**: Tuple-unpack fix — restores ticket ingestion; ChromaDB ticket collection will now be populated.
- **`services/action/handlers/write_handler.py`** and **`path_validator.py`**: `atomic_write_json` returns byte count; write_handler removes redundant `json.dumps`.
- **`services/action/handlers/ticket_handler.py`**: Four handler functions simplified; extracted helper tested separately.
- **`services/approval/main.py`**, **`services/audit/main.py`**, **`services/memory/main.py`**, **`services/knowledge/main.py`**, **`services/orchestrator/main.py`**: Unused import removal only — zero runtime change.
- **`services/approval/queue.py`**: TTL and docstring corrections.
- **`frontend/app.py`**: Approval URL reads from env var — correct behaviour in deployed environments.
- **`shared/http_client.py`**: Extended with per-component timeout and `service_headers()` — callers updated; no API breakage.
- **CI**: `ruff check` should pass clean after unused-import removals.
- **No database schema changes. No API contract changes. No breaking changes.**

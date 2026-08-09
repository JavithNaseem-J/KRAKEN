## 1. Critical Crash Fixes

- [x] 1.1 Add `from collections.abc import Callable` to `services/action/main.py` imports — fixes the NameError that prevents the action service from starting
- [x] 1.2 Rename `settings.memory_service_url` → `settings.memory_url` in `services/orchestrator/main.py:277` (`_fetch_session_messages`) — fixes the AttributeError that silently discards session history on every `/run` call
- [x] 1.3 Change `chunks, _ = load_ticket_chunks()` → `chunks = load_ticket_chunks()` on line 95 of `scripts/ingest_knowledge.py` — fixes the ValueError that prevents ticket data from ever loading into ChromaDB

## 2. Dead Code Removal

- [x] 2.1 Remove `import secrets` and `Header` from `from fastapi import ...` in `services/approval/main.py` (neither is used directly; auth is via `verify_service_token`)
- [x] 2.2 Remove `import secrets` and `Header` from `from fastapi import ...` in `services/audit/main.py`
- [x] 2.3 Remove `import secrets` and `Header` from `from fastapi import ...` in `services/memory/main.py`
- [x] 2.4 Remove `import secrets` from `services/knowledge/main.py`
- [x] 2.5 Remove `import secrets` and `Header` from `from fastapi import ...` in `services/orchestrator/main.py`
- [x] 2.6 Move `import json` and `import uuid` from inside `retrieve()` method body to module-level imports in `services/knowledge/retriever.py`

## 3. Shared HTTP Client Factory

- [x] 3.1 Update `create_async_http_client()` in `shared/http_client.py` to accept an optional `timeout: httpx.Timeout | None = None` parameter; use a default of `httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)` when `None`
- [x] 3.2 Add `service_headers(token: str | None = None) -> dict[str, str]` function to `shared/http_client.py` that reads `get_settings().hitl_service_token` when `token` is `None`
- [x] 3.3 Replace the inline `httpx.AsyncClient(timeout=httpx.Timeout(...))` construction in `services/gateway/main.py` lifespan with `create_async_http_client()`
- [x] 3.4 Replace the inline `httpx.AsyncClient(timeout=httpx.Timeout(...))` construction in `services/approval/main.py` lifespan with `create_async_http_client()`
- [x] 3.5 Replace inline `{"X-Service-Token": settings.hitl_service_token}` dict literals in `services/gateway/main.py` with `service_headers()`
- [x] 3.6 Replace inline `{"X-Service-Token": settings.hitl_service_token}` dict literal in `services/approval/main.py` `_notify_orchestrator_callback` with `service_headers()`
- [x] 3.7 Replace inline service-token header dicts in `services/orchestrator/main.py` HTTP calls with `service_headers()`

## 4. Atomic Write Deduplication

- [x] 4.1 Change `atomic_write_json(target_path, content) -> None` signature to `-> int` in `services/action/safety/path_validator.py`; return `len(json_bytes)` after the write
- [x] 4.2 In `services/action/handlers/write_handler.py`: remove the redundant `json_bytes = json.dumps(content, ...).encode(...)` on line 66; replace `len(json_bytes)` in the return dict and log call with the return value of `atomic_write_json()`
- [x] 4.3 Update the call site in `services/action/handlers/ticket_handler.py` (`_save_tickets`) to handle the new `int` return type (or ignore it — `_save_tickets` does not use it)

## 5. Ticket Lookup Helper

- [x] 5.1 Add `_find_ticket(tickets: list[dict[str, Any]], ticket_id: str) -> dict[str, Any] | None` at module level in `services/action/handlers/ticket_handler.py`; implement case-insensitive `.strip().upper()` match on `ticket["id"]`
- [x] 5.2 Refactor `execute_auto_respond` to use `_find_ticket()` instead of the inline scan loop; raise `ActionExecutionError` when `None`
- [x] 5.3 Refactor `execute_escalate` to use `_find_ticket()` instead of the inline scan loop; raise `ActionExecutionError` when `None`
- [x] 5.4 Refactor `execute_request_info` to use `_find_ticket()` instead of the inline scan loop; raise `ActionExecutionError` when `None`
- [x] 5.5 Refactor `execute_close` to use `_find_ticket()` instead of the inline scan loop; raise `ActionExecutionError` when `None`

## 6. Pattern Consistency Fixes

- [x] 6.1 Move `settings = get_settings()` in `services/action/audit_client.py` from inside the async function body to module level (matching every other module)
- [x] 6.2 In `services/approval/queue.py`: update `pipe.expire(_INDEX, self._timeout)` to use `self._timeout + 3600` so the index outlives the newest entry by one hour; fix the docstring to remove the reference to the never-implemented shadow-meta key
- [x] 6.3 In `frontend/app.py`: replace both hardcoded `"http://localhost:8004"` strings with `os.getenv("APPROVAL_URL", "http://localhost:8004")` resolved once at module level as `_APPROVAL_URL`

## 7. Verification

- [x] 7.1 Run `ruff check .` — confirm zero errors (unused imports removed, in-function imports moved)
- [x] 7.2 Run `ruff format --check .` — confirm zero format violations
- [x] 7.3 Run `mypy shared/ services/` — confirm no new type errors from `atomic_write_json` return-type change or `service_headers` addition
- [x] 7.4 Run `pytest tests/unit -v --tb=short` — confirm all existing tests pass (109/109 passed)
- [x] 7.5 Manually verify: import `services.action.main` in a Python shell — confirm no `NameError` on `Callable`
- [x] 7.6 Manually verify: run `python scripts/ingest_knowledge.py` (or `make ingest`) — confirm tickets are printed in the summary count and no `ValueError` is raised (17 tickets, 28 total chunks successfully ingested)

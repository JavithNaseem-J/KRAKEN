## 1. Bug Fixes (Live Issues)

- [x] 1.1 Fix episodic memory chunk key mismatch in `services/orchestrator/graph/nodes/retriever.py`: change `"text"` → `"content"` and `"score"` → `"relevance_score"` in the episodic chunk dict built in `retrieve_node` so the reasoner receives non-empty episodic context
- [x] 1.2 Fix semaphore TOCTOU race in `services/orchestrator/main.py`: replace the `if semaphore.locked(): raise 503` pre-check + `await semaphore.acquire()` pair with a single `asyncio.wait_for(semaphore.acquire(), timeout=0.0)` call wrapped in a `try/except asyncio.TimeoutError` that raises the 503
- [x] 1.3 Fix CSRF fail-open in `services/approval/queue.py` `verify_csrf_token()`: change both `return True` fallback branches (missing token and Redis exception) to `return False`; remove the "test environment" bypass comment

## 2. Security Hardening

- [x] 2.1 Add `Depends(verify_service_token)` to `GET /history/{session_id}` and `GET /history/user/{user_id}` in `services/audit/main.py`
- [x] 2.2 Delete the `POST /v1/approval-callback` route from `services/gateway/main.py`, its `_BYPASS_PATHS` entry in `services/gateway/middleware/auth.py`, and its test in `tests/unit/test_gateway.py`
- [x] 2.3 Add `environment: Literal["dev", "staging", "prod"] = "dev"` to `shared/config.py` `Settings`; add a `@model_validator(mode="after")` that raises `ValueError` if `hitl_service_token == "change-me-in-production"` and `environment != "dev"`; document `ENVIRONMENT` in `.env.example`

## 3. Shared Audit Contract

- [x] 3.1 Create `shared/models/audit.py` with `AuditLogRequest` Pydantic model containing all 11 fields currently spread across `audit/main.py` and `audit_client.py`
- [x] 3.2 Update `services/audit/main.py` to import `AuditLogRequest` from `shared.models.audit` (delete the local definition); update the `POST /log` endpoint body type
- [x] 3.3 Update `services/audit/audit_store.py` `log_action()` to accept an `AuditLogRequest` instance directly (replacing the 11-keyword-argument signature) and extract fields internally
- [x] 3.4 Update `services/action/audit_client.py` to import and construct `AuditLogRequest` from `shared.models.audit`, call `.model_dump()` for the POST body
- [x] 3.5 Update any orchestrator node that assembles audit payloads (`decider.py`, `memory_writer.py` if applicable) to use the shared model

## 4. Knowledge Service Cache Removal

- [x] 4.1 Remove the `query_cache_col` collection creation and the `"query_cache"` entry from `collections` in `services/knowledge/main.py` lifespan
- [x] 4.2 Delete the semantic cache lookup block (cache hit path) from `services/knowledge/retriever.py` `retrieve()` method
- [x] 4.3 Delete the semantic cache write block from `services/knowledge/retriever.py` `retrieve()` method
- [x] 4.4 Verify all existing knowledge service tests still pass after removal

## 5. Action Service — Ticket Handler Consolidation

- [x] 5.1 Remove `_get_redis_client()`, `_get_db_lock()`, the module-level `_redis_client` global, and all `import redis` statements from `services/action/handlers/ticket_handler.py`
- [x] 5.2 Add `_tickets_lock = threading.Lock()` (module-level) and replace all `with _get_db_lock():` usages with `with _tickets_lock:`
- [x] 5.3 Extract `_mutate_ticket(ticket_id: str, new_status: str, extra_fields: dict) -> dict` helper implementing the shared lock/load/find/update/save/log pattern
- [x] 5.4 Refactor `execute_escalate`, `execute_request_info`, and `execute_close` to be thin argument-validation wrappers that delegate to `_mutate_ticket`
- [x] 5.5 Remove `asyncpg` from `services/action/requirements.txt`
- [x] 5.6 Run `tests/unit/test_action.py` to confirm all ticket-handler tests pass

## 6. HTTP Client Normalisation

- [x] 6.1 Update `services/action/main.py` lifespan: replace the raw `httpx.AsyncClient(timeout=httpx.Timeout(...))` construction with `create_async_http_client()` imported from `shared.http_client`
- [x] 6.2 Add a persistent HTTP client to the orchestrator lifespan (`app.state.http = create_async_http_client()`); update `_fetch_session_messages()` to use `app.state.http` instead of the inline `async with httpx.AsyncClient(...)` block; close it in shutdown
- [x] 6.3 Verify `executor.py` and `retriever.py` module-level clients are closed in the orchestrator's lifespan shutdown block (add explicit `executor._http_client.aclose()` and `retriever._http_client.aclose()` calls if not already present)

## 7. Orchestrator Fixes

- [x] 7.1 Make semaphore size and worker count env-configurable: add `ORCHESTRATOR_MAX_CONCURRENCY: int = 5` and `ORCHESTRATOR_WORKERS: int = 4` to `shared/config.py`; read them in `orchestrator/main.py` lifespan instead of hardcoded literals
- [x] 7.2 Fix `prune_stale_checkpoints()` in `services/orchestrator/main.py`: add a `DELETE FROM checkpoint_writes WHERE thread_id IN (...)` statement using the same stale-session subquery already used for the `checkpoints` table; update `deleted_counts["checkpoint_writes"]` correctly
- [x] 7.3 Remove the `inspect.isawaitable()` shim from `services/approval/main.py`: replace `set_res = queue.set_csrf_token(...); if inspect.isawaitable(set_res): await set_res` with `await queue.set_csrf_token(...)`; same for `verify_csrf_token`; remove `import inspect`

## 8. Knowledge Service Requirements Fix

- [x] 8.1 Rewrite `services/knowledge/requirements.txt`: remove `langchain`, `langchain-community`, `asyncpg`; add `langchain-huggingface` with a pinned version matching the root `requirements.txt`; verify the image builds and the service starts without `ModuleNotFoundError`

## 9. Seed Data Deduplication

- [x] 9.1 Delete the hardcoded `SAMPLE_TICKETS` list from `scripts/seed_data.py`; replace the seed logic with `shutil.copy2("data/knowledge/tickets/sample_tickets.json", "data/workspace/tickets.json")` (or remove the script entirely)
- [x] 9.2 Update the `Makefile` `seed` target comment if the script changes; verify `make seed` produces a correct `data/workspace/tickets.json`

## 10. Repository Housekeeping

- [x] 10.1 Run `git rm -r --cached data/chroma/` to stop tracking the committed ChromaDB binaries
- [x] 10.2 Add `data/chroma/` to `.gitignore`
- [x] 10.3 Add `data/workspace/*.json` and `data/workspace/*.bak.json` to `.gitignore` (workspace files are runtime artifacts, not source)
- [x] 10.4 Commit the `.gitignore` updates and the `git rm` result together

## 11. README and render.yaml

- [x] 11.1 Create `README.md` at the repository root with: one-paragraph project overview, prerequisites list (Python 3.12, Docker Compose, Groq API key), 5-command quickstart (`cp .env.example .env` → set keys → `make up` → `make ingest` → `make eval`), link to `docs/architecture.md`, and a GitHub Actions CI badge
- [x] 11.2 Expand `render.yaml` to add the 5 missing web services: `akea-action` (port 8003), `akea-approval` (port 8004), `akea-memory` (port 8005), `akea-knowledge` (port 8002), `akea-audit` (port 8006) with their correct env vars
- [x] 11.3 Add `APPROVAL_URL: https://akea-approval.onrender.com` to the `akea-frontend` service env in `render.yaml`
- [x] 11.4 Remove the hardcoded default API key value from `frontend/app.py` `st.text_input` (change `value="dev-key-alice-longer-secure-key"` to `value=os.getenv("GATEWAY_API_KEY", "")`)

## 12. Verification

- [x] 12.1 Run `pytest tests/unit -v --tb=short` — all tests must pass
- [x] 12.2 Run `ruff check . && ruff format --check .` — zero lint errors
- [x] 12.3 Run `mypy shared/ services/ --ignore-missing-imports` — zero type errors introduced by this change
- [x] 12.4 Start services locally (`make up`) and send a test message through the frontend to confirm end-to-end flow still works
- [x] 12.5 Verify the approval CSRF fail-closed fix: submit a decision form without a CSRF token and confirm HTTP 403 is returned
- [x] 12.6 Verify unauthenticated audit history returns 403: `curl http://localhost:8006/history/test-session` without `X-Service-Token` must return 403

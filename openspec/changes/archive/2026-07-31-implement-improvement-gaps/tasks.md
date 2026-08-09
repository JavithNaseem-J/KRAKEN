## 1. Security Guardrails

- [x] 1.1 Add CSRF token generation in `services/approval/main.py` `GET /approve/{approval_id}` and validation in `POST /approve/{approval_id}/decision`

## 2. Concurrency Control & Resilience

- [x] 2.1 Initialize bounded `ThreadPoolExecutor(max_workers=4)` and `asyncio.Semaphore(5)` in `services/orchestrator/main.py` lifespan state
- [x] 2.2 Protect `/run` endpoint with semaphore capacity check, returning HTTP 503 Service Unavailable when full

## 3. Distributed Tracing & Observability

- [x] 3.1 Update `service_headers()` in `shared/http_client.py` to accept optional `trace_id` and include `"X-Trace-Id"`
- [x] 3.2 Inject `trace_id` header in gateway proxy calls and orchestrator graph node HTTP client requests

## 4. Performance & Cache Guardrails

- [x] 4.1 Add `CREATE INDEX IF NOT EXISTS` DDL statements for `session_id` and `user_id` on `audit_log` and `episodic_memory` tables in `scripts/init.sql`
- [x] 4.2 Enforce 1,800-character max length cap on `chunks_json` cache metadata in `services/knowledge/retriever.py`

## 5. Tooling & Documentation

- [x] 5.1 Create `scripts/check_health.py` to aggregate all 7 microservice health checks
- [x] 5.2 Add `status` and auto-documenting `help` targets to `Makefile`
- [x] 5.3 Create `docs/architecture.md` with Mermaid sequence (HITL lifecycle) and component dependency diagrams
- [x] 5.4 Update `README.md` to link and embed the architecture diagrams
- [x] 5.5 Add `deploy` job to `.github/workflows/ci.yml` triggering Render deploy hook on `main` branch pushes

## 6. Verification

- [x] 6.1 Run `ruff check .` — confirm zero errors across all files
- [x] 6.2 Run `pytest tests/unit -v --tb=short` — confirm all unit tests pass (109/109 passed)
- [x] 6.3 Run `python scripts/check_health.py` — confirm health check script executes cleanly

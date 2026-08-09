## 1. Edge & Security Guardrails

- [x] 1.1 Add `QueryRequest.model_validate(body)` validation to `services/gateway/main.py` `/v1/run` endpoint before proxying.
- [x] 1.2 Add `cors_allowed_origins` setting in `shared/config.py` `Settings` and update `CORSMiddleware` in `services/gateway/main.py` and `services/approval/main.py`.
- [x] 1.3 Update `AuditStore.log_action()` in `services/audit/audit_store.py` to use `ISOLATION LEVEL SERIALIZABLE` for concurrent write protection.

## 2. Production Observability & Container Basics

- [x] 2.1 Create `shared/middleware/trace_id.py` (or shared trace ID middleware helper) and register across all microservices to bind `X-Trace-Id` to `structlog.contextvars`.
- [x] 2.2 Add `HEALTHCHECK` instructions using `python -c "import httpx..."` to all 7 service Dockerfiles (`services/*/Dockerfile`).
- [x] 2.3 Update `docker-compose.yml` to specify `{ condition: service_healthy }` for upstream application dependencies.
- [x] 2.4 Add shutdown flag and semaphore draining logic to lifespan in `services/orchestrator/main.py`.

## 3. Performance & Frontend Polish

- [x] 3.1 Wrap `_dispatch()` in `asyncio.to_thread(_dispatch, ...)` in `services/action/main.py` `/execute` handler.
- [x] 3.2 Add LRU session eviction (keep 20 most recent by `updated_at`) in `frontend-react/src/App.tsx`.

## 4. Documentation & CI Portfolio Signals

- [x] 4.1 Update `README.md` to reference the React frontend (`http://localhost:5173`) instead of Streamlit.
- [x] 4.2 Create `.github/workflows/ci.yml` running lint (`ruff check .`), type-check (`mypy shared/ services/`), unit tests (`pytest tests/ -v`), and docker compose health validation.

## 5. Verification

- [x] 5.1 Run full test suite `pytest tests/ -v` and health check `python scripts/check_health.py` to confirm zero regressions.

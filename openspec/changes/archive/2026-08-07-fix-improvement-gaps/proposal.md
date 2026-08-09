## Why

A systematic audit identified 15 improvement gaps (5 high-severity) across missing guardrails, production basics, scalability, modern stack, and portfolio signals. The system cannot be deployed to production without addressing the top gaps: the gateway bypasses its own Pydantic validation, CORS origins are hardcoded to localhost, there is no trace-ID correlation across 7 services, Dockerfiles lack health checks, and the README references a Streamlit frontend that doesn't exist. These are blocking issues, not nice-to-haves.

## What Changes

- **MG-1: Gateway request validation** — Enforce `QueryRequest.model_validate()` on `/v1/run` body before proxying to orchestrator. Return 422 on invalid payloads.
- **MG-3: Configurable CORS origins** — Add `cors_allowed_origins` to `shared/config.py` `Settings`. Parse as comma-separated list. Use in gateway and approval CORSMiddleware.
- **MG-4: Audit hash chain concurrency protection** — Wrap `log_action()` read-previous + insert in a serializable transaction to prevent chain forking under concurrent writes.
- **PB-1: Trace ID middleware** — Add `TraceIdMiddleware` to all services that extracts `X-Trace-Id` / `X-Request-Id` from headers and binds to `structlog.contextvars`, so all logs for a request share a correlation key.
- **PB-2: Dockerfile HEALTHCHECK** — Add `HEALTHCHECK` instructions to all 7 service Dockerfiles. Add application service health conditions to `docker-compose.yml` `depends_on`.
- **PB-3: Orchestrator graceful shutdown** — Add shutdown flag + semaphore drain to orchestrator lifespan so in-flight graph runs complete before process exit.
- **SG-2: Async ticket handler** — Wrap sync `_dispatch()` in `asyncio.to_thread()` to stop blocking the event loop.
- **SG-3: Frontend session eviction** — Add LRU eviction (keep last 20 sessions) to `localStorage` persistence in `App.tsx`.
- **PS-1: Fix README** — Replace Streamlit reference with React frontend URL. 
- **PS-2: Add CI workflow** — Create `.github/workflows/ci.yml` running `ruff check`, `mypy`, `pytest`, and Docker health gate.

**Deferred** (not in scope):
- MG-2 (ML prompt injection classifier) — requires model hosting decisions and dependency evaluation.
- SG-1 (embedding service extraction) — requires architecture decision on microservice vs cloud provider.
- MS-1 (OpenTelemetry) — deferred to a dedicated change after trace-ID propagation is in place.
- MS-2 (SSE streaming) — large scope, requires LangGraph streaming integration.
- MS-3 (API versioning) — low priority, single consumer.

## Capabilities

### New Capabilities

- `gateway-request-validation`: Pydantic validation of `/v1/run` request body at the gateway before proxy.
- `configurable-cors`: Environment-driven CORS origin configuration for production deployment.
- `trace-id-middleware`: Cross-service trace ID extraction and structlog binding middleware.
- `dockerfile-healthchecks`: Docker HEALTHCHECK instructions for all service containers.
- `orchestrator-graceful-shutdown`: Semaphore-draining shutdown for in-flight graph runs.
- `ci-workflow`: GitHub Actions CI pipeline running lint, type-check, test, and Docker health gate.
- `frontend-session-eviction`: LRU session eviction in frontend localStorage persistence.

### Modified Capabilities

- `gateway-input-guardrails`: Adding Pydantic validation step before proxy (MG-1).
- `audit-contract`: Adding concurrent-write protection to hash chain (MG-4).
- `docker-standardization`: Adding HEALTHCHECK to Dockerfiles and health conditions to compose (PB-2).
- `orchestrator-concurrency-control`: Adding graceful shutdown semaphore drain (PB-3).
- `readme-and-onboarding`: Fixing frontend URL reference (PS-1).
- `action-dispatch`: Wrapping sync dispatch in `asyncio.to_thread()` (SG-2).

## Impact

- **New files**: `.github/workflows/ci.yml`, `shared/middleware/trace_id.py` (or similar)
- **Modified files**: `services/gateway/main.py`, `services/approval/main.py`, `shared/config.py`, `services/audit/audit_store.py`, all 7 `services/*/Dockerfile`, `docker-compose.yml`, `services/orchestrator/main.py`, `services/action/main.py`, `frontend-react/src/App.tsx`, `README.md`
- **New dependencies**: None (structlog contextvars, asyncio.to_thread are stdlib/already installed)
- **API changes**: Gateway will now return 422 (instead of forwarding invalid requests). This is a **corrective** change — previously invalid requests reached the orchestrator and failed there with less informative errors.
- **Docker changes**: Dockerfiles gain HEALTHCHECK. Compose gains service health conditions for `depends_on`.

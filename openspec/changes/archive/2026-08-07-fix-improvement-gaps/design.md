## Context

KRAKEN is a 7-service FastAPI microservice system. An audit found 15 improvement gaps. This change addresses the 10 that are feasible without new external dependencies or large architectural changes. The system currently: (a) bypasses its own Pydantic validation at the gateway, (b) has hardcoded localhost CORS, (c) has no cross-service log correlation, (d) has no Docker health checks on application services, (e) has a race condition in the audit hash chain, (f) has no graceful shutdown in the orchestrator, (g) blocks the event loop in the action service, (h) has unbounded localStorage in the frontend, (i) references a nonexistent Streamlit frontend in the README, and (j) has no CI pipeline despite a CI badge.

## Goals / Non-Goals

**Goals:**
- Close the gateway input validation gap (MG-1)
- Make CORS origins configurable via environment (MG-3)
- Protect audit hash chain integrity under concurrent writes (MG-4)
- Enable cross-service request correlation via trace ID structlog binding (PB-1)
- Add Docker HEALTHCHECK to all service Dockerfiles (PB-2)
- Add graceful shutdown with semaphore drain to orchestrator (PB-3)
- Stop the action service's sync handler from blocking the event loop (SG-2)
- Prevent frontend localStorage overflow with LRU session eviction (SG-3)
- Fix the stale README Streamlit reference (PS-1)
- Add a working GitHub Actions CI workflow (PS-2)

**Non-Goals:**
- ML-based prompt injection classification (MG-2) — deferred, needs model hosting decision
- Embedding microservice extraction (SG-1) — architectural decision, separate change
- Full OpenTelemetry instrumentation (MS-1) — depends on trace-ID middleware landing first
- SSE streaming responses (MS-2) — large scope, separate change
- API versioning strategy (MS-3) — low priority

## Decisions

### D-1: Gateway validation approach

**Decision**: Add `QueryRequest.model_validate(body)` in the `/v1/run` handler, between `request.json()` and `_proxy()`. Return 422 on `ValidationError`.

**Rationale**: The `QueryRequest` model already exists with correct constraints. This is a 5-line change. The gateway currently forwards raw JSON — validation should happen at the edge.

**Alternative considered**: Add validation as middleware. Rejected — middleware can't easily return Pydantic 422 detail format, and the validation is endpoint-specific.

---

### D-2: CORS configuration

**Decision**: Add `cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000"` to `Settings` in `shared/config.py`. Parse as `settings.cors_allowed_origins.split(",")` in both gateway and approval `CORSMiddleware`. Strip whitespace.

**Rationale**: Follows the existing pattern of comma-separated config strings (e.g., `gateway_api_keys`). No new dependencies.

**Alternative considered**: JSON list in env var. Rejected — comma-separated is simpler and consistent with existing patterns.

---

### D-3: Audit hash chain concurrency protection

**Decision**: Use `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE` around the `SELECT max(entry_hash)` + `INSERT` sequence in `log_action()`.

**Rationale**: Serializable isolation guarantees that concurrent transactions reading the same `previous_hash` will conflict at commit time — the second transaction will be rolled back by Postgres with a serialization failure. The caller retries (asyncpg handles this with a simple retry loop).

**Alternative considered**: Advisory lock (`pg_advisory_xact_lock`). Viable but serializable isolation is more idiomatic and doesn't require choosing a lock ID.

---

### D-4: Trace ID middleware

**Decision**: Create `shared/middleware/trace_id.py` with a `TraceIdMiddleware(BaseHTTPMiddleware)` that: (1) reads `X-Trace-Id` or `X-Request-Id` from request headers, (2) generates a UUID if missing, (3) calls `structlog.contextvars.bind_contextvars(trace_id=trace_id)`, (4) adds `X-Trace-Id` to the response headers, (5) clears contextvars after the request.

**Rationale**: Structlog's contextvars integration is zero-config — once `bind_contextvars(trace_id=...)` is called, every `log.*()` call in that request context automatically includes the trace ID. This is a pure middleware addition with no changes to existing log call sites.

**Alternative considered**: OpenTelemetry `TraceContext` propagation. Deferred — OTEL is a larger dependency with configuration overhead. The trace-ID middleware is the prerequisite that makes OTEL adoption easier later.

---

### D-5: Dockerfile HEALTHCHECK

**Decision**: Add `HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import httpx; httpx.get('http://localhost:<PORT>/health').raise_for_status()"]` to each service Dockerfile. Use Python+httpx (already installed) instead of `curl` (not in `python:3.11-slim`).

**Rationale**: `curl` isn't available in the slim Python image. `httpx` is already a dependency. A one-line Python check is reliable and doesn't require installing additional packages.

**Alternative considered**: `wget`. Available in some slim images but not guaranteed. Python+httpx is already there.

---

### D-6: Orchestrator graceful shutdown

**Decision**: Add a `_shutting_down` flag (module-level `asyncio.Event`) checked in `/run` and `/approval-callback`. On lifespan shutdown, set the flag and acquire the semaphore N times (N = max_concurrency) with a 30-second timeout to drain in-flight runs.

**Rationale**: The semaphore already bounds concurrency. Acquiring all N slots means all in-flight runs have released. The event flag rejects new work with 503 during drain.

**Alternative considered**: `signal.signal(SIGTERM, handler)`. Doesn't compose well with uvicorn's own signal handling. The lifespan approach is FastAPI-idiomatic.

---

### D-7: Async ticket dispatch

**Decision**: Wrap the sync `_dispatch()` call in `asyncio.to_thread(_dispatch, action, payload)` inside the `/execute` route handler.

**Rationale**: Minimal change — one line. The sync handler continues working unchanged but runs off the event loop thread. Full async migration (psycopg_pool.AsyncConnectionPool) is a larger refactor for a future change.

---

### D-8: Frontend session eviction

**Decision**: Before saving to localStorage, sort sessions by `updated_at` descending and keep only the 20 most recent. Drop older sessions.

**Rationale**: 20 sessions × ~50KB average ≈ 1MB, well within localStorage's 5-10MB limit. Simple, no IndexedDB complexity.

---

## Risks / Trade-offs

- **[Risk] Gateway 422 errors may surprise existing clients** → Mitigation: The only client is the React frontend, which already constructs valid payloads. This catches malformed API calls, not legitimate use.

- **[Risk] Serializable isolation on audit writes has retry overhead** → Mitigation: Audit writes are low-frequency (one per action execution). Conflict rate will be negligible.

- **[Risk] `asyncio.to_thread` for ticket handler creates a thread per request** → Mitigation: Default thread pool is 40 threads (Python 3.12). Ticket mutations are infrequent. Full async migration is planned for a future change.

- **[Risk] Session eviction drops old sessions without warning** → Mitigation: 20 is generous for a demo/portfolio app. A production version would use IndexedDB or server-side persistence.

## Migration Plan

1. Changes are backward-compatible — no data migrations, no breaking API changes (422 is corrective).
2. Docker changes require `docker compose build` to pick up new Dockerfiles.
3. CORS changes require setting `CORS_ALLOWED_ORIGINS` env var for non-localhost deployments.
4. CI workflow activates automatically on push once `.github/workflows/ci.yml` is committed.
5. Rollback: `git revert` on any change group.

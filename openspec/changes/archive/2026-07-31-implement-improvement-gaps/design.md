## Context

Following structural debt remediation, `REPORT2_IMPROVEMENT_GAPS.md` identified high-value improvements across security guardrails, concurrency management, distributed tracing, database index performance, cache overflow protection, diagnostic tooling, and system architecture visualization.

## Goals / Non-Goals

**Goals:**
- Implement `X-Trace-Id` header injection and propagation across inter-service HTTP clients.
- Add form-based CSRF protection or token verification to approval decision submissions (`POST /approve/{approval_id}/decision`).
- Add bounded execution pool (`ThreadPoolExecutor(max_workers=4)`) and `asyncio.Semaphore(max_conc=5)` to orchestrator `graph.invoke` to prevent thread exhaustion under load.
- Add performance indexes for `session_id` and `user_id` on `audit_log` and `episodic_memory` tables in `scripts/init.sql`.
- Cap `chunks_json` string length at 1,800 characters before caching in `services/knowledge/retriever.py`.
- Create `scripts/check_health.py` to aggregate all 7 microservice health checks, and wire it to `make status` and an auto-documenting `make help`.
- Create `docs/architecture.md` with Mermaid sequence (HITL lifecycle) and component dependency diagrams, linked in `README.md`.
- Add Render deployment trigger job to `.github/workflows/ci.yml`.

**Non-Goals:**
- No full framework migration (keep FastAPI, LangGraph, Streamlit).
- No external OAuth2 identity provider integration (keep current API key & service token auth).

## Decisions

### D1 — `X-Trace-Id` Header Propagation via `service_headers()`

**Decision:** Update `service_headers()` in `shared/http_client.py` to accept `trace_id: str | None = None`. If provided, include `"X-Trace-Id": trace_id`. If `None` and an active trace exists via structlog/OpenTelemetry, extract or auto-generate a UUID4.

### D2 — CSRF Protection on Approval Decision Form

**Decision:** The `GET /approve/{approval_id}` route generates a short-lived CSRF token stored in Redis `akea:csrf:{approval_id}` and renders it in a hidden form field. The `POST /approve/{approval_id}/decision` route verifies the submitted token matching Redis.

### D3 — Bounded Graph Execution Pool in Orchestrator

**Decision:** Initialize `app.state.graph_executor = ThreadPoolExecutor(max_workers=4)` and `app.state.graph_semaphore = asyncio.Semaphore(5)` in `services/orchestrator/main.py` lifespan. If `app.state.graph_semaphore.locked()` when a request arrives, return HTTP 503 Service Unavailable immediately.

### D4 — Cache Metadata Size Cap

**Decision:** In `services/knowledge/retriever.py`, before inserting query cache entries, check `len(chunks_json)`. If `len(chunks_json) > 1800`, truncate the list of chunks to top 2 or omit the `chunks_json` metadata key to stay safely under ChromaDB's 2,048-char metadata limit.

## Risks / Trade-offs

- **CSRF token TTL** → Token expires if user waits too long on approval page. Mitigation: TTL set to approval timeout length (900s).
- **Concurrency cap 503s** → Rejection under extreme load. Mitigation: Prevents worker thread starvation and cascading system crashes; 503 allows gateway to retry or surface clean error to user.

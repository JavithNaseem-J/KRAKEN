## Why

Following the structural debt fixes, the repository audit in `REPORT2_IMPROVEMENT_GAPS.md` identified 27 improvement opportunities across security, observability, concurrency, and operational signal. Crucially, the approval decision endpoint currently accepts unauthenticated POST requests, orchestrator graph executions use an unbounded thread pool, audit queries lack database indexes, and system topology is undocumented. Addressing these gaps elevates AKEA to production-ready engineering standards.

## What Changes

- **Add Distributed Tracing Propagation**: Update `shared/http_client.py` and node HTTP callers to propagate `X-Trace-Id` across inter-service calls.
- **Secure Approval Decision Endpoint**: Protect `POST /approve/{approval_id}/decision` in `services/approval/main.py` with CSRF validation / URL signature checks.
- **Add Bounded Concurrency & Semaphores in Orchestrator**: Replace unbounded thread pool execution of `graph.invoke` with a bounded `ThreadPoolExecutor(max_workers=4)` and an `asyncio.Semaphore` returning 503 when full.
- **Add Database Indexes for Audit & Episodic Memory**: Add missing B-tree indexes on `session_id` and `user_id` in `scripts/init.sql`.
- **Add Semantic Cache Metadata Size Guardrail**: Enforce a 1,800-character cap on `chunks_json` metadata in `services/knowledge/retriever.py` to prevent ChromaDB metadata overflow.
- **Add System Health Aggregator Script**: Add `scripts/check_health.py` to query all 7 service health endpoints and wire it to `make status` and an auto-documented `make help` target.
- **Add Visual Architecture Diagrams**: Create `docs/architecture.md` containing Mermaid sequence (HITL flow) and component topology diagrams, and embed them in `README.md`.
- **Add CI/CD Deployment Workflow**: Update `.github/workflows/ci.yml` with a Render deployment trigger job on `main` branch pushes.

## Capabilities

### New Capabilities

- `distributed-tracing-propagation`: Automatic propagation of `X-Trace-Id` headers across inter-service HTTP requests.
- `approval-security-guardrail`: CSRF and authentication enforcement on HITL approval decision submissions.
- `orchestrator-concurrency-control`: Bounded thread pool execution and request concurrency throttling on agent graph execution.
- `health-aggregator-tooling`: Multi-service status aggregator script and enhanced Makefile commands.
- `architecture-documentation`: Visual Mermaid sequence and component architecture specifications in `docs/architecture.md`.

### Modified Capabilities

- `knowledge-cache`: Added a 1,800-character size guardrail on stored metadata chunks to prevent vector store corruption.

## Impact

- **`shared/http_client.py`**: Accepts `trace_id` parameter in `service_headers()`.
- **`services/approval/main.py`**: Adds CSRF form validation to approval HTML forms and decision route.
- **`services/orchestrator/main.py`**: Manages bounded `ThreadPoolExecutor` and `Semaphore` in lifespan state.
- **`services/knowledge/retriever.py`**: Truncates cache metadata before ChromaDB upsert.
- **`scripts/init.sql`**: Added `CREATE INDEX IF NOT EXISTS` DDL statements.
- **`scripts/check_health.py`**: New diagnostic tool script.
- **`docs/architecture.md`**: New documentation file with Mermaid diagrams.
- **`.github/workflows/ci.yml`**: Added deploy job.

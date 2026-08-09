## Why

A systematic audit of the KRAKEN codebase identified 16 structural debt issues across 5 categories (6 high-severity). The highest-impact problems — duplicated DDL logic, a circular import that blocks testability, and dead code polluting the canonical state contract — are cheap to fix now and will compound in cost if left until the codebase scales.

## What Changes

- **Extract `shared/db/tickets.py`**: Deduplicate the identical `CREATE TABLE tickets` DDL and seeding logic currently copy-pasted between `services/action/handlers/ticket_handler.py` and `scripts/seed_data.py`.
- **Extract `ensure_collection()` helper**: Deduplicate the identical Qdrant collection-create block in `services/knowledge/main.py` and `services/knowledge/ingest.py`.
- **Add `create_async_redis_client()` to `shared/http_client.py`**: Replace the copy-pasted `aioredis.from_url(...)` call (same 5 kwargs) in `ShortTermMemory`, `ApprovalQueue`, and `SlidingWindowRateLimiter`.
- **Delete `services/knowledge/embedder.py`**: Remove the 8-line re-export shim; update the 3 internal import sites to pull from `shared.embedder` directly.
- **Delete `AgentStateModel`**: Remove the dead Pydantic model from `shared/models/agent.py` (never imported anywhere; the real state contract is `GraphState(TypedDict)`).
- **Remove inert multi-step plan fields**: Delete `plan`, `completed_steps` from `GraphState` and remove the dead conditional routing that reads them but is never triggered.
- **Fix circular import in `memory_writer.py`**: Replace `from services.orchestrator.main import app` with a module-level context variable set during lifespan, so unit tests can inject a mock HTTP client.
- **Add `done_callback` to `asyncio.create_task` usages**: Surface silently-dropped exceptions in `memory_writer.py` and `approval/main.py`.
- **Rename `_rerank_candidates` → `_heuristic_rerank`**: Fix the misleading docstring that claims "cross-encoder re-ranking".
- **Delete `tests/integration/`**: Remove empty placeholder directory.

## Capabilities

### New Capabilities

- `shared-ticket-db-helpers`: Shared module (`shared/db/tickets.py`) exposing `ensure_tickets_table()` and `seed_tickets()` so DDL is defined once. *(Note: `shared-ticket-lookup` already exists as a spec; this extends DB lifecycle concerns, not lookup.)*
- `shared-redis-client-factory`: `create_async_redis_client(url)` factory in `shared/http_client.py` — mirrors the existing `create_async_http_client` pattern.
- `memory-writer-context-var`: Context-variable pattern in `services/orchestrator/` so `memory_writer_node` receives the HTTP client without a circular import.

### Modified Capabilities

- `shared-http-client`: Adding `create_async_redis_client()` extends this module's factory surface.
- `knowledge-loader-consolidation`: The `ensure_collection()` extraction touches the ingestion flow spec'd here.

## Impact

- **Files deleted**: `services/knowledge/embedder.py`, `tests/integration/__init__.py`, `AgentStateModel` class in `shared/models/agent.py`
- **Files modified**: `services/action/handlers/ticket_handler.py`, `scripts/seed_data.py`, `services/knowledge/main.py`, `services/knowledge/ingest.py`, `services/knowledge/retriever.py`, `services/memory/short_term.py`, `services/approval/queue.py`, `services/gateway/middleware/rate_limiter.py`, `services/orchestrator/graph/state.py`, `services/orchestrator/graph/agent_graph.py`, `services/orchestrator/graph/nodes/memory_writer.py`, `services/orchestrator/main.py`, `shared/http_client.py`, `shared/models/agent.py`
- **No API changes** — all modifications are internal to service boundaries; the public REST API surface is unchanged.
- **No dependency additions** — all fixes use stdlib or packages already in `requirements.txt`.
- **Tests**: Existing unit tests for `ticket_handler`, `short_term`, `approval_queue`, and `orchestrator` nodes should continue to pass. The circular-import fix will make `test_graph_nodes.py` easier to mock.

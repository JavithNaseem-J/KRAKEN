## Context

The KRAKEN codebase currently has 16 structural debt issues identified by a systematic audit. This design covers the 10 actionable fixes: 2 extraction of shared helpers, 1 Redis factory, 1 shim deletion, 2 dead-code removals, 1 circular-import elimination, 1 exception-surfacing improvement, and 1 misleading rename.

No new external dependencies are introduced. All changes are strictly internal to existing module boundaries. The public REST API is unaffected.

## Goals / Non-Goals

**Goals:**
- Ensure ticket DDL is defined in exactly one place (`shared/db/tickets.py`).
- Ensure Qdrant collection creation is defined in exactly one place (`knowledge/ingest.py::ensure_collection()`).
- Ensure Redis client construction uses a single shared factory (`shared/http_client.create_async_redis_client()`).
- Remove the `services/knowledge/embedder.py` re-export shim.
- Remove the dead `AgentStateModel` Pydantic class.
- Remove the inert `plan` / `completed_steps` fields and the dead routing branch.
- Eliminate the circular import in `memory_writer.py` by replacing it with a module-level context variable.
- Add `done_callback` to bare `asyncio.create_task()` calls so exceptions surface in logs.
- Rename `_rerank_candidates` to `_heuristic_rerank` with corrected docstring.
- Delete the empty `tests/integration/` stub directory.

**Non-Goals:**
- Implementing multi-step planning (DC-3 removal is a cleanup, not a feature build-out).
- Migrating ticket handlers to fully async (that is IP-3, tracked in Report 2 / future work).
- Any changes to the public API, data models, or Docker configuration.
- Performance improvements or scalability changes.

## Decisions

### D-1: Where to place the shared ticket DB helpers

**Decision**: New file `shared/db/tickets.py`.

**Rationale**: `shared/db/` already has a `__init__.py` that exports `create_pool`. Ticket lifecycle concerns (DDL + seed) belong in the data layer alongside the pool factory. Placing it here keeps the `ticket_handler.py` handler focused on business logic, not schema management.

**Alternative considered**: Inline the deduplication inside `ticket_handler.py` and have `seed_data.py` import from it. Rejected because a `services/` module importing into a `scripts/` helper inverts the dependency direction.

---

### D-2: Where to place `ensure_collection()`

**Decision**: Add `ensure_collection(client, collection_name, vector_size=384)` to `services/knowledge/ingest.py`.

**Rationale**: Both call-sites are already in the `services/knowledge/` namespace. `ingest.py` is the authoritative home for Qdrant write operations. Moving it to `shared/cache.py` would pull a service-specific concern (384-dim knowledge collection) into the shared layer.

**Alternative considered**: `shared/cache.py`. Rejected — it would require `shared/` to know about the knowledge service's vector dimension, which is service-specific config.

---

### D-3: Redis client factory placement

**Decision**: Add `create_async_redis_client(url: str) -> aioredis.Redis` to `shared/http_client.py`.

**Rationale**: `shared/http_client.py` already houses `create_async_http_client()` using the exact same factory pattern. Adding the Redis variant here keeps all network-client factories in one discoverable location. The existing `redis.asyncio` dependency is already in `requirements.txt`.

**Alternative considered**: New `shared/redis_client.py`. Overkill for a single small function.

---

### D-4: Circular import fix for `memory_writer.py`

**Decision**: Add a module-level `contextvars.ContextVar` or a plain module-level variable `_http_client: httpx.AsyncClient | None = None` with a `set_http_client(client)` setter. The orchestrator's lifespan calls `set_http_client(app.state.http)` on startup. `memory_writer_node` reads from the module variable instead of importing the app.

**Rationale**: Avoids the deferred `from services.orchestrator.main import app` anti-pattern. The module variable is a simple, testable seam — tests call `set_http_client(mock_client)` without touching FastAPI.

**Alternative considered**: Pass `http_client` through `GraphState`. Rejected — it would add a framework-level object (AsyncClient) to the domain state, making state serialization/deserialization fragile for LangGraph checkpointing.

---

### D-5: Handling `asyncio.create_task` exception surfacing

**Decision**: Add `.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)` on all bare `create_task()` calls in `memory_writer.py` and `approval/main.py`.

**Rationale**: This is the minimal change to prevent exception silencing without restructuring the background-task architecture. `t.exception()` will re-raise the exception in the callback, which Python then logs as an unhandled exception in the asyncio task context (appears in structlog output).

---

## Risks / Trade-offs

- **[Risk] `shared/db/tickets.py` imports `psycopg_pool` (sync pool)** → If `shared/` is imported in a context that doesn't install `psycopg_pool`, it will fail. *Mitigation*: Keep the import inside the function body, guarded by the existing `try/except` pattern already used in `ticket_handler.py`.

- **[Risk] Deleting `plan` / `completed_steps` fields removes an advertised (if unimplemented) feature** → If someone started building on those fields in a branch, the removal will conflict. *Mitigation*: The audit confirmed no node writes to these fields. The removal is safe; multi-step planning can be re-introduced properly when needed.

- **[Risk] Context variable pattern for HTTP client is a module-level singleton** → In tests that run multiple service lifespans in the same process, `set_http_client` could leak between tests. *Mitigation*: Add a `clear_http_client()` counterpart called in test teardown.

## Migration Plan

1. All changes are backward-compatible at the API level — no data migrations required.
2. Changes should be applied in the task order: shared helpers first, then consumers.
3. Run `pytest tests/ -v` after each task group to validate no regressions.
4. Rollback: all changes are in Python source files under version control — `git revert` is the rollback strategy.

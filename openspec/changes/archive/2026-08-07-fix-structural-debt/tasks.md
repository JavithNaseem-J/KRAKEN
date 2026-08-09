## 1. Extract Shared Database & Client Helpers

- [x] 1.1 Create `shared/db/tickets.py` containing `ensure_tickets_table(conn)` and `seed_tickets(conn, data)`.
- [x] 1.2 Update `services/action/handlers/ticket_handler.py` and `scripts/seed_data.py` to delegate to `shared/db/tickets.py`.
- [x] 1.3 Add `create_async_redis_client(url)` in `shared/http_client.py`.
- [x] 1.4 Update `ShortTermMemory.__init__`, `ApprovalQueue.__init__`, and `SlidingWindowRateLimiter.__init__` to use `create_async_redis_client()`.
- [x] 1.5 Extract `ensure_collection(client, collection_name, vector_size)` in `services/knowledge/ingest.py` and update `services/knowledge/main.py` to use it.

## 2. Eliminate Re-exports, Dead Code & Inert Structures

- [x] 2.1 Delete `services/knowledge/embedder.py` shim and update import sites in `ingest.py`, `retriever.py`, and `main.py` to import from `shared.embedder`.
- [x] 2.2 Delete unused `AgentStateModel` class in `shared/models/agent.py`.
- [x] 2.3 Remove unused `plan` and `completed_steps` fields from `GraphState` in `services/orchestrator/graph/state.py` and update `_route_after_execution` in `agent_graph.py`.
- [x] 2.4 Delete empty `tests/integration/` directory.

## 3. Fix Circular Imports & Task Error Handling

- [x] 3.1 Introduce module-level HTTP client setter/getter context in `services/orchestrator/graph/nodes/memory_writer.py` and invoke setter in `services/orchestrator/main.py` lifespan.
- [x] 3.2 Remove `from services.orchestrator.main import app` from `memory_writer_node`.
- [x] 3.3 Add exception-logging done-callbacks to `asyncio.create_task` calls in `memory_writer.py` and `services/approval/main.py`.
- [x] 3.4 Rename `_rerank_candidates` to `_heuristic_rerank` in `services/knowledge/retriever.py` and update docstring to accurately reflect heuristic boosting.

## 4. Verification

- [x] 4.1 Run unit test suite `pytest tests/ -v` to ensure zero regressions.

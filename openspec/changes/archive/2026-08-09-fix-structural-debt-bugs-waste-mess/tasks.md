## 1. High-Severity Bug Fixes

- [x] 1.1 Add missing `import re` to `services/action/handlers/ticket_handler.py`
- [x] 1.2 Update `services/orchestrator/observability.py` to pass `secret_key` and `host` to Langfuse `CallbackHandler`
- [x] 1.3 Extract shared HTTP POST retry helper `post_with_retry` into `shared/http_client.py` and update orchestrator `executor.py` and `retriever.py` to use it
- [x] 1.4 Create `shared/constants.py` with `TICKET_ID_REGEX` and replace duplicate ticket ID regexes across knowledge and orchestrator services

## 2. Medium & Low Structural Debt Cleanup

- [x] 2.1 Refactor `services/action/main.py` `_dispatch()` to use dynamic handler registry mapping instead of manual `if/elif` chain
- [x] 2.2 Convert `memory_writer_node` in `services/orchestrator/graph/nodes/memory_writer.py` to `async def` and bind HTTP client to `app.state.http`
- [x] 2.3 Consolidate load benchmark scripts into `scripts/benchmark.py` and deprecate `test_load_concurrency.py`
- [x] 2.4 Fix UUID return type annotation and casting in `services/audit/audit_store.py`
- [x] 2.5 Extract inline stop-words set in `services/knowledge/retriever.py` to a module-level `frozenset` constant
- [x] 2.6 Clean unused sync `build_graph()` and dead `TYPE_CHECKING` imports in `services/orchestrator/graph/agent_graph.py` and dead imports in `services/knowledge/main.py`

## 3. Verification

- [x] 3.1 Run Pytest unit test suite (`uv run pytest tests/unit`) and validate change with `openspec validate`

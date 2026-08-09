# Tasks: Fix Medium-Severity Structural & Code Quality Debt

## 1. Models, Exceptions, and Shared Utilities

- [x] 1.1 Remove unused `AgentState` from `shared/models/agent.py` and update comment in `services/orchestrator/graph/state.py`.
- [x] 1.2 Remove 12 unused exception classes from `shared/exceptions.py`.
- [x] 1.3 Create `shared/logging.py` and invoke `configure_logging()` in the lifespan of all 7 microservices.
- [x] 1.4 Create `shared/http_client.py` and refactor orchestrator graph nodes (`retriever.py`, `executor.py`, `memory_writer.py`) to use it.

## 2. Action Service & File I/O Refactoring

- [x] 2.1 Extract `atomic_write_json` helper into `shared/path_validator.py` and update `write_handler.py` and `ticket_handler.py`.
- [x] 2.2 Refactor `services/action/main.py` `_dispatch` to use dictionary handler mapping driven by `shared/registry.py`.
- [x] 2.3 Delete `data/workspace/tickets.json` from git and consolidate ticket loading to use `data/knowledge/tickets/sample_tickets.json` as seed.

## 3. Knowledge, Orchestrator, & Database Cleanup

- [x] 3.1 Remove Redis exact-match cache from `services/orchestrator/graph/nodes/retriever.py`.
- [x] 3.2 Remove unused `tickets` DDL table and indexes from `scripts/init.sql` and simplify `load_ticket_chunks()`.
- [x] 3.3 Enforce `verify_service_token` on `/maintenance/prune-checkpoints` endpoint in `services/orchestrator/main.py`.
- [x] 3.4 Delete dead function `_resolve_risk_level` from `services/orchestrator/graph/nodes/decider.py` and update unit tests.
- [x] 3.5 Use `settings.llm_temperature` in `services/orchestrator/llm.py` and remove unused `llm_provider` and `langsmith_*` settings.
- [x] 3.6 Remove `sqlalchemy[asyncio]` from requirements files in `action`, `audit`, and `knowledge` services.

## 4. Verification

- [x] 4.1 Run full unit test suite `pytest tests/unit` to verify clean execution.

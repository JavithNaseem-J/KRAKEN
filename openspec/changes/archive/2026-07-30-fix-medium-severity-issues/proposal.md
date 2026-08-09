# Proposal: Fix Medium-Severity Structural & Code Quality Debt

## Why

The codebase contains 13 medium-severity code quality, structural, and performance issues across models, exception handling, file I/O, cache strategy, DDL schemas, logging configuration, HTTP client instantiation, authentication, and service requirements. Resolving these eliminates dead code, fixes ticket data split-brain, standardizes logging/HTTP clients across all 7 services, removes redundant cache layers, and aligns action dispatching directly with the action registry.

## What Changes

- **Models & Exceptions (`shared/`)**:
  - Remove duplicate `AgentState` from `shared/models/agent.py` and update stale comment in `services/orchestrator/graph/state.py`.
  - Remove 12 unused exception classes from `shared/exceptions.py`.
- **File I/O & Ticket Data**:
  - Extract atomic JSON write helper into `services/action/safety/atomic_write.py` and use in both `ticket_handler._save_tickets` and `write_handler.write_json_file`.
  - Unify ticket loading with a single `load_tickets(path)` helper. Keep `data/knowledge/tickets/sample_tickets.json` as the single committed source of truth and delete `data/workspace/tickets.json` from git.
- **Action Service Dispatch**:
  - Bind action handlers directly to registry definitions in `shared/registry.py` or map via registry metadata in `services/action/main.py`, replacing the manual `if/elif` dispatch chain.
- **Cache Streamlining**:
  - Remove redundant Redis exact-match cache in `services/orchestrator/graph/nodes/retriever.py`, relying on ChromaDB's semantic cache layer in the Knowledge service.
- **Postgres Schema & Ingest Cleanup**:
  - Remove unused `tickets` DDL table and indexes from `scripts/init.sql` and simplify `load_ticket_chunks()` in `services/knowledge/loaders/ticket_loader.py`.
- **Logging & HTTP Client Standardization**:
  - Create `shared/logging.py` and invoke `configure_logging()` in all 7 services during lifespan.
  - Create `shared/http_client.py` for shared inter-service HTTP client creation and header formatting.
- **Authentication & Code Cleanup**:
  - Update `/maintenance/prune-checkpoints` in `services/orchestrator/main.py` to use timing-safe `verify_service_token`.
  - Delete unused `_resolve_risk_level` function in `decider.py` and update unit tests.
  - Hardcode/configure `llm_temperature` from settings in `services/orchestrator/llm.py` and remove unused `llm_provider` and `langsmith_*` settings/dependencies.
  - Remove unused `sqlalchemy[asyncio]` from requirements files in `action`, `audit`, and `knowledge` services.

## Capabilities

### New Capabilities
- `shared-logging`: Centralized structlog configuration shared across all 7 services.
- `shared-http-client`: Reusable HTTP client and inter-service authentication header helper.
- `atomic-file-writer`: Shared atomic file persistence utility.

### Modified Capabilities
- `action-dispatch`: Dynamic handler binding for action execution without duplicate parameter checks.
- `knowledge-cache`: Single-layer semantic caching for knowledge retrieval.

## Impact

- **Shared**: `shared/models/agent.py`, `shared/exceptions.py`, `shared/config.py`, `shared/logging.py`, `shared/http_client.py`.
- **Services**: `gateway`, `orchestrator`, `action`, `approval`, `knowledge`, `memory`, `audit`.
- **Data & Database**: `data/workspace/tickets.json` deleted; `scripts/init.sql` cleaned.

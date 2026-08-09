# Design Document: Fix Medium-Severity Structural & Code Quality Debt

## Context

A systematic code audit identified 13 medium-severity issues spanning duplicate state models, unused exception classes, duplicated atomic file write blocks, split-brain ticket dataset loaders, manual if/elif action dispatching, double caching layers, leftover DDL schema tables, inconsistent structlog initialization, duplicated HTTP client instantiation in orchestrator nodes, divergent authentication on maintenance endpoints, dead code in decider nodes, hardcoded LLM temperature, and bloat in service requirements files.

## Goals / Non-Goals

**Goals:**
- Eliminate unused exception classes, dead helper functions, duplicate state schemas, and obsolete settings/dependencies.
- Unify structlog configuration in `shared/logging.py` and call it across all 7 services.
- Unify HTTP client instantiation and inter-service headers in `shared/http_client.py`.
- Extract atomic JSON file persistence into `shared/path_validator.py` or `services/action/safety/atomic_write.py`.
- Consolidate ticket dataset loading and delete duplicate committed `data/workspace/tickets.json`.
- Streamline retrieval caching to ChromaDB's semantic cache collection.
- Clean unused DDL table `tickets` from `scripts/init.sql`.

**Non-Goals:**
- Modifying core graph topology or HITL approval flow rules.

## Technical Decisions

1. **Shared Utilities**:
   - `shared/logging.py`: Centralized `configure_logging()` helper.
   - `shared/http_client.py`: Centralized HTTP client creation and `service_headers()`.
   - `shared/path_validator.py`: `atomic_write_json(path, data)`.
2. **Action Dispatch Refactoring**:
   - Map action names to handlers via dictionary lookup in `services/action/main.py` using `shared/registry.py` keys.
3. **Data Split-Brain Resolution**:
   - `data/knowledge/tickets/sample_tickets.json` remains the master seed; workspace copy is generated dynamically at runtime if absent.

## Risks / Trade-offs

- [Risk] Unused exception removal breaks third-party imports → Mitigation: Grep codebase before deletion to confirm 0 references.

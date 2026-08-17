## Context

The audit identified critical structural debt across the KRAKEN codebase, including duplicate authentication and rate-limiting middleware in Gateway vs shared modules, a 1,020-line monolithic `services/orchestrator/main.py`, 7 duplicated per-service Dockerfiles and requirements manifests, and fragmented database / logging patterns.

## Goals / Non-Goals

**Goals:**
- Consolidate security and rate limiting middleware into `shared/auth.py` and `shared/middleware/rate_limit.py`, removing duplicate files in `services/gateway/middleware/`.
- Modularize `services/orchestrator/main.py` into clean submodules (`graph/nodes.py`, `graph/router.py`, `prompts.py`, `telemetry.py`).
- Centralize dependency manifests into root `pyproject.toml` and streamline container builds using `Dockerfile.standalone`.
- Standardize database ticket access via `shared.db.tickets` and logging via `shared.logging.setup_logging()`.

**Non-Goals:**
- Redesigning external HTTP endpoint schemas or modifying frontend React UI components.
- Rewriting underlying LLM decider logic or LangChain graph algorithms.

## Decisions

### Decision 1: Single Source of Truth for Auth and Rate-Limiting Middleware
We will delete [`services/gateway/middleware/auth.py`](file:///F:/DSML/KRAKEN/services/gateway/middleware/auth.py) and [`services/gateway/middleware/rate_limiter.py`](file:///F:/DSML/KRAKEN/services/gateway/middleware/rate_limiter.py) in favor of [`shared/auth.py`](file:///F:/DSML/KRAKEN/shared/auth.py) and [`shared/middleware/rate_limit.py`](file:///F:/DSML/KRAKEN/shared/middleware/rate_limit.py).
- *Rationale*: Eliminates security drift and inconsistent rate limit key tracking across services.

### Decision 2: Modular Orchestrator Decomposition
We will decompose [`services/orchestrator/main.py`](file:///F:/DSML/KRAKEN/services/orchestrator/main.py) (1,020 lines) into:
- `services/orchestrator/graph/nodes.py`: Node execution handlers (decider, responder, human-in-the-loop gate).
- `services/orchestrator/graph/router.py`: Graph edge routing condition functions.
- `services/orchestrator/prompts.py`: Prompt template constants and dynamic string formatters.
- `services/orchestrator/telemetry.py`: Telemetry and tracing helpers.
- `services/orchestrator/main.py`: Lightweight FastAPI application setup and endpoint routes (~150 lines).

### Decision 3: Dependency and Build Artifact Consolidation
We will remove individual `services/*/requirements.txt` files and `services/*/Dockerfile` duplicates, maintaining dependency groups in [`pyproject.toml`](file:///F:/DSML/KRAKEN/pyproject.toml) and building images via [`Dockerfile.standalone`](file:///F:/DSML/KRAKEN/Dockerfile.standalone).

## Risks / Trade-offs

- **[Risk] Test Import Breakage**: Unit tests referencing `services.gateway.middleware.auth` will fail after file deletion.
  - *Mitigation*: Update unit tests in `tests/unit/test_gateway.py` to import from `shared.auth`.
- **[Risk] Orchestrator Circular Imports**: Splitting nodes, routers, and main app can introduce circular imports.
  - *Mitigation*: Maintain state schema in `services/orchestrator/graph/state.py` and pass `AgentState` explicitly without importing `main.py`.

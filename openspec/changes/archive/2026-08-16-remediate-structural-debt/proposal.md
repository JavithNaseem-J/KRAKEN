## Why

The KRAKEN codebase currently accumulates structural debt from duplicate authentication and rate-limiting middleware in Gateway vs shared modules, a 1,020-line monolithic `services/orchestrator/main.py`, 7 redundant per-service Dockerfiles and requirements manifests, and fragmented database and logging abstractions. Remediating this debt now eliminates security drift, reduces maintenance friction, and improves overall code quality and modularity.

## What Changes

- **Consolidate Middleware**: Remove redundant [`services/gateway/middleware/auth.py`](file:///F:/DSML/KRAKEN/services/gateway/middleware/auth.py) and [`services/gateway/middleware/rate_limiter.py`](file:///F:/DSML/KRAKEN/services/gateway/middleware/rate_limiter.py), unifying on [`shared/auth.py`](file:///F:/DSML/KRAKEN/shared/auth.py) and [`shared/middleware/rate_limit.py`](file:///F:/DSML/KRAKEN/shared/middleware/rate_limit.py).
- **Modularize Orchestrator**: Refactor the 1,020-line monolithic [`services/orchestrator/main.py`](file:///F:/DSML/KRAKEN/services/orchestrator/main.py) into dedicated submodules (`graph/nodes.py`, `graph/router.py`, `prompts.py`, `telemetry.py`).
- **Consolidate Build & Dependency Configurations**: Migrate dependency management from 7 per-service `requirements.txt` files into root [`pyproject.toml`](file:///F:/DSML/KRAKEN/pyproject.toml) and parameterize container builds via [`Dockerfile.standalone`](file:///F:/DSML/KRAKEN/Dockerfile.standalone).
- **Standardize Database & Logging Patterns**: Delegate ticket queries to [`shared/db/tickets.py`](file:///F:/DSML/KRAKEN/shared/db/tickets.py) and enforce consistent JSON logging via [`shared/logging.py`](file:///F:/DSML/KRAKEN/shared/logging.py).

## Capabilities

### New Capabilities

- `shared-middleware-consolidation`: Unified authentication verification and sliding-window rate limiting middleware for all microservices.
- `orchestrator-modularization`: Modularized LangGraph agent state graph, node handlers, prompt definitions, and telemetry tracing.

### Modified Capabilities

*No existing spec requirements are changing.*

## Impact

- **Affected Services**: `services/gateway/`, `services/orchestrator/`, `services/action/`, `shared/`
- **Dependencies**: `pyproject.toml`, Docker configuration, `shared.auth`, `shared.middleware`

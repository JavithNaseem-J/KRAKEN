## 1. Middleware Consolidation

- [x] 1.1 Remove redundant [`services/gateway/middleware/auth.py`](file:///F:/DSML/KRAKEN/services/gateway/middleware/auth.py) and update Gateway routes to import `verify_service_token` from [`shared.auth`](file:///F:/DSML/KRAKEN/shared/auth.py).
- [x] 1.2 Remove redundant [`services/gateway/middleware/rate_limiter.py`](file:///F:/DSML/KRAKEN/services/gateway/middleware/rate_limiter.py) and update Gateway routes to import rate-limiting middleware from [`shared.middleware.rate_limit`](file:///F:/DSML/KRAKEN/shared/middleware/rate_limit.py).
- [x] 1.3 Update Gateway unit tests in [`tests/unit/test_gateway.py`](file:///F:/DSML/KRAKEN/tests/unit/test_gateway.py) to reflect consolidated middleware import paths.

## 2. Orchestrator Modularization

- [x] 2.1 Extract prompt templates and string formatters into [`services/orchestrator/prompts.py`](file:///F:/DSML/KRAKEN/services/orchestrator/prompts.py).
- [x] 2.2 Extract telemetry tracing utilities into [`services/orchestrator/telemetry.py`](file:///F:/DSML/KRAKEN/services/orchestrator/telemetry.py).
- [x] 2.3 Create [`services/orchestrator/graph/nodes/`](file:///F:/DSML/KRAKEN/services/orchestrator/graph/nodes) containing node handlers (`decider_node`, `responder_node`, `hitl_gate_node`).
- [x] 2.4 Create [`services/orchestrator/graph/router.py`](file:///F:/DSML/KRAKEN/services/orchestrator/graph/router.py) containing conditional edge routing logic (`route_next_step`).
- [x] 2.5 Refactor [`services/orchestrator/main.py`](file:///F:/DSML/KRAKEN/services/orchestrator/main.py) to assemble the graph from submodules and serve FastAPI routes concisely (~150 lines).

## 3. Dependency & Artifact Cleanup

- [x] 3.1 Consolidate per-service dependencies into [`pyproject.toml`](file:///F:/DSML/KRAKEN/pyproject.toml) and remove duplicate `services/*/requirements.txt` files.
- [x] 3.2 Remove duplicate `services/*/Dockerfile` files and update [`docker-compose.yml`](file:///F:/DSML/KRAKEN/docker-compose.yml) to reference parameterized container builds or [`Dockerfile.standalone`](file:///F:/DSML/KRAKEN/Dockerfile.standalone).
- [x] 3.3 Remove [`kraken_shared.egg-info/`](file:///F:/DSML/KRAKEN/kraken_shared.egg-info) build directory from workspace root and update `.gitignore`.

## 4. Verification

- [x] 4.1 Run unit test suite (`pytest`) to ensure zero regressions across gateway, orchestrator, and shared modules.
- [x] 4.2 Run local health check probes across Gateway (`http://localhost:8000/health`) and Orchestrator (`http://localhost:8001/health`).

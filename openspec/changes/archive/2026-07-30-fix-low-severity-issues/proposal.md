## Why

This proposal addresses 6 low-severity structural, code quality, and consistency debt issues discovered during the full codebase audit. Resolving these eliminates dead surface area, aligns dev environment API keys across tests and scripts, fixes Docker build encoding errors, standardizes service Dockerfiles, and consolidates dependency declarations.

## What Changes

- **Delete Root Dev Script**: Remove `scratch_schema.py` from repository root.
- **Docker Standardization**: Fix UTF-16 encoding corruptions in `services/gateway/Dockerfile` and standardize all 6 service Dockerfiles onto a consistent multi-stage build pattern.
- **Dependency Consolidation**: Ensure root `requirements.txt` acts as the complete master union of all service dependencies.
- **API Key Standardization**: Standardize the default dev API key (`dev-key-alice-longer-secure-key`) across `frontend/app.py`, `scripts/benchmark.py`, `tests/evals/eval_harness.py`, `shared/config.py`, and `.env.example`.
- **Dead Code Removal**: Remove unused `_ALL_SOURCES` in `retriever.py`, and unused fields (`requires_hitl`, `approval_id`) from `ActionResult` in `shared/models/action.py`.
- **Gateway Main Startup**: Parse and validate gateway API keys once at module level in `services/gateway/main.py` and reuse in `lifespan`.

## Capabilities

### New Capabilities
- `docker-standardization`: Standard multi-stage container builds and unified dependency management.
- `dev-key-alignment`: Unified default API key configuration across frontend, CLI scripts, and evaluation harness.

### Modified Capabilities
*(None - no requirement changes to existing core spec contracts)*

## Impact

- **Files Deleted**: `scratch_schema.py`
- **Files Modified**: `services/*/Dockerfile`, `requirements.txt`, `frontend/app.py`, `scripts/benchmark.py`, `tests/evals/eval_harness.py`, `shared/config.py`, `.env.example`, `services/orchestrator/graph/nodes/retriever.py`, `shared/models/action.py`, `services/gateway/main.py`.

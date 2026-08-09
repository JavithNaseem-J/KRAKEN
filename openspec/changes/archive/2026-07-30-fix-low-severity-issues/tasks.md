# Tasks: Fix Low-Severity Structural & Code Quality Debt

## 1. Dead Code Removal & Startup Optimization

- [x] 1.1 Delete `scratch_schema.py` from repository root.
- [x] 1.2 Remove unused `_ALL_SOURCES` from `services/orchestrator/graph/nodes/retriever.py`.
- [x] 1.3 Remove unused fields (`requires_hitl`, `approval_id`) from `ActionResult` in `shared/models/action.py`.
- [x] 1.4 Refactor `services/gateway/main.py` to parse API keys once at module level.

## 2. API Key Alignment & Documentation

- [x] 2.1 Standardize default dev API key (`dev-key-alice-longer-secure-key`) across `frontend/app.py`, `scripts/benchmark.py`, `tests/evals/eval_harness.py`, `shared/config.py`, and `.env.example`.

## 3. Dockerfiles & Dependency Synchronization

- [x] 3.3 Fix character encoding in `services/gateway/Dockerfile` and standardize all 6 microservice Dockerfiles onto multi-stage build pattern.
- [x] 3.4 Synchronize root `requirements.txt` to contain all dependencies required across microservices.

## 4. Verification

- [x] 4.1 Run full unit test suite `pytest tests/unit` to verify 100% clean test pass.

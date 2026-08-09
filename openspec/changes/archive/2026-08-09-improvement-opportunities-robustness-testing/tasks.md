## 1. High-Impact Additions & Security Hardening

- [x] 1.1 Add per-action payload schema validation against `REGISTRY` parameter schemas in `services/action/main.py`
- [x] 1.2 Expose `GET /approve/{approval_id}/details` JSON endpoint in `services/approval/main.py` and update `frontend-react/src/services/api.ts`
- [x] 1.3 Add rate limiting middleware to approval endpoints in `services/approval/main.py`
- [x] 1.4 Add aggregated `/ready` probe to `services/gateway/main.py` checking liveness across all downstream services

## 2. Compliance, Observability & Error Contracts

- [x] 2.1 Emit audit log entry on Gateway `SemanticCache` hits (`cache_hit`)
- [x] 2.2 Define canonical `ErrorResponse` model in `shared/models/error.py`
- [x] 2.3 Propagate unified `X-Trace-Id` / `X-Request-Id` across all inter-service calls and background tasks

## 3. Integration Testing & Migration Tooling

- [x] 3.1 Create `tests/integration/` end-to-end integration test suite verifying gateway -> orchestrator -> action -> audit flow
- [x] 3.2 Add Alembic database migration setup (`alembic.ini`, `migrations/`) for schema evolution
- [x] 3.3 Run unit & integration test suites (`uv run pytest tests/unit tests/integration`) and validate change with `openspec validate`

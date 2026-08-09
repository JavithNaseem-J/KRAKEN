## Why

Following the senior AI/ML engineer audit, Report 2 identified 14 improvement opportunities across security, testing, compliance, resilience, and API design. Implementing these key architectural enhancements will secure LLM payload execution, enforce end-to-end auditability (including semantic cache hits), eliminate fragile frontend HTML scraping with structured JSON approval endpoints, introduce end-to-end integration testing, and provide unified system readiness probes.

## What Changes

- **Security & Payload Validation**:
  - Enforce per-action `parameter_schema` validation in decider/executor before forwarding payloads to action execution endpoints.
  - Add IP rate limiting on public approval endpoints (`GET /approve/{id}` & `POST /approve/{id}/decision`).
- **Observability & Compliance**:
  - Standardize error responses using a unified `ErrorResponse` model in `shared/models/error.py`.
  - Log an audit record when the gateway returns a response from `SemanticCache` (`cache_hit`).
  - Propagate a consistent `X-Trace-Id` / `X-Request-Id` across all inter-service calls, background tasks, and audit logs.
- **API Cleanups & Frontend Reliability**:
  - Expose `GET /approve/{approval_id}/details` returning JSON to replace fragile frontend HTML scraping.
  - Add `/ready` aggregated health endpoint on API Gateway that checks downstream microservice liveness.
- **Testing & Tooling**:
  - Add `tests/integration/` test suite to verify end-to-end HTTP flows across microservices.
  - Add Alembic DB migration configuration (`alembic.ini`, `migrations/`) for schema evolution.

## Capabilities

### New Capabilities

- `system-robustness-and-observability`: Enforces payload validation, canonical error handling, cache audit logging, approval JSON endpoints, gateway readiness probes, and integration test coverage.

### Modified Capabilities

None.

## Impact

- `services/action/` & `services/orchestrator/`: Added schema validation for action payloads.
- `services/approval/`: Added `GET /approve/{approval_id}/details` JSON endpoint and rate limiting.
- `services/gateway/`: Added `/ready` endpoint and audit logging for cache hits.
- `frontend-react/src/services/api.ts`: Updated to call JSON approval details endpoint.
- `shared/models/`: Added `ErrorResponse` model.
- `tests/integration/`: Created integration test suite.

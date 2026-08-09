## Context

Report 2 of the codebase audit outlined 14 improvement opportunities focusing on payload security, system-wide trace correlation, API reliability, integration testing, and readiness probes.

## Goals / Non-Goals

**Goals:**

- Validate LLM-generated action payloads against registered action parameter schemas in `shared/registry.py` before execution.
- Expose a clean JSON endpoint (`GET /approve/{approval_id}/details`) on the approval service so the frontend React application does not regex-scrape HTML templates.
- Emit audit log entries when queries hit the Gateway's `SemanticCache`.
- Expose a `/ready` endpoint on the API Gateway that checks liveness across orchestrator, knowledge, action, approval, memory, and audit services.
- Provide canonical `ErrorResponse` schemas in `shared/models/error.py`.
- Add integration test suite under `tests/integration/`.

**Non-Goals:**

- Changing the core LangGraph state machine flow or rewriting database schemas.

## Decisions

- **Decision 1: Action Payload Validation**: Use Pydantic / jsonschema in `services/action/main.py` to validate `ActionRequest.payload` against the action's `parameter_schema` in `REGISTRY`.
- **Decision 2: JSON Approval Details Endpoint**: Add `GET /approve/{approval_id}/details` in `services/approval/main.py` returning `ApprovalDetailsResponse` (session_id, action_name, payload, reasoning, status, csrf_token).
- **Decision 3: Gateway Readiness Aggregation**: `GET /ready` in `services/gateway/main.py` executes concurrent `GET /health` requests to all dependent microservices with a 2-second timeout and returns 200 OK or 503 Service Unavailable.

## Risks / Trade-offs

- **Risk**: Strict payload schema validation might fail on loosely structured LLM parameters.
  - **Mitigation**: Ensure default actions in `REGISTRY` allow optional string fields with fallback defaults.

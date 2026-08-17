## Context

Following Report 2 findings, the project requires production guardrails around API request validation, environment configuration assertion, and frontend React UI component error handling.

## Goals / Non-Goals

**Goals:**
- Implement Pydantic schema validation for incoming Gateway API endpoints (`/v1/run`, `/v1/approval`, `/v1/knowledge/query`).
- Add startup environment validation in `shared/config.py` asserting non-default secret keys when `ENVIRONMENT=prod`.
- Wrap React drawer and chat stream components in `frontend-react/src/App.tsx` with a React Error Boundary.

**Non-Goals:**
- Modifying underlying microservice communication protocols or database schemas.

## Decisions

### Decision 1: Gateway Endpoint Pydantic Schema Validation
Define explicit Pydantic request models in [`services/gateway/main.py`](file:///F:/DSML/KRAKEN/services/gateway/main.py):
- `RunQueryRequest`: `message: str`, `session_id: Optional[str]`, `user_id: Optional[str]`
- `ApprovalCallbackRequest`: `decision: str`, `approval_id: str`, `reason: Optional[str]`
- `KnowledgeQueryRequest`: `query: str`, `top_k: Optional[int]`

### Decision 2: Production Secret Assertion
Add `validate_production_secrets()` validation method to `Settings` in [`shared/config.py`](file:///F:/DSML/KRAKEN/shared/config.py). If `ENVIRONMENT == "prod"`, verify secret attributes (`LLM_API_KEY`, `GATEWAY_API_KEY`, `HITL_SERVICE_TOKEN`) are present and do not equal default development fallback strings.

### Decision 3: Frontend Component Error Boundaries
Import [`frontend-react/src/components/ErrorBoundary.tsx`](file:///F:/DSML/KRAKEN/frontend-react/src/components/ErrorBoundary.tsx) in `App.tsx` and enclose `TelemetryDrawer`, `ReasoningInspectorDrawer`, and chat view components within error boundary tags.

## Risks / Trade-offs

- **[Risk] Malformed Client Requests**: Clients sending arbitrary JSON payloads to `/v1/run` will receive `422 Unprocessable Entity` instead of `500 Internal Server Error`.
  - *Mitigation*: Ensure 422 JSON response body clearly details missing/invalid schema attributes.

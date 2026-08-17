## Why

The system currently lacks explicit Pydantic request validation schemas on Gateway endpoints, relies on in-memory rate limiting fallbacks, permits default development secrets in production environments, and lacks global React Error Boundary protection around SSE stream drawers. Addressing these gaps hardens API security, prevents silent UI crashes, and ensures production readiness.

## What Changes

- **Gateway Pydantic Request Validation**: Define explicit Pydantic request models (`RunQueryRequest`, `ApprovalCallbackRequest`, `KnowledgeQueryRequest`) in [`services/gateway/main.py`](file:///F:/DSML/KRAKEN/services/gateway/main.py) to validate request structure, field types, and body constraints before forwarding downstream.
- **Production Secret Validation**: Enforce strict environment validation in [`shared/config.py`](file:///F:/DSML/KRAKEN/shared/config.py) on application startup, raising runtime configuration errors if default development tokens (`dev-token`, `dev-secret-key`) are present when `ENVIRONMENT=prod`.
- **Resilient Rate Limit Tracking**: Update [`shared/middleware/rate_limit.py`](file:///F:/DSML/KRAKEN/shared/middleware/rate_limit.py) to maintain persistent rate limit counters and prevent key reset vulnerabilities across restart cycles.
- **Frontend Error Boundaries**: Wrap SSE drawer and chat components in [`frontend-react/src/App.tsx`](file:///F:/DSML/KRAKEN/frontend-react/src/App.tsx) with [`components/ErrorBoundary.tsx`](file:///F:/DSML/KRAKEN/frontend-react/src/components/ErrorBoundary.tsx) to catch rendering exceptions gracefully.

## Capabilities

### New Capabilities

- `gateway-request-validation`: Pydantic input schema validation enforcing structured request payloads on Gateway endpoints.
- `production-secret-validation`: Startup environment checks asserting mandatory production keys when running in production mode.
- `frontend-error-boundaries`: React Error Boundary wrapper insulating UI views from unhandled stream or drawer component errors.

### Modified Capabilities

*No existing spec requirements are changing.*

## Impact

- **Affected Modules**: `services/gateway/`, `shared/config.py`, `shared/middleware/`, `frontend-react/src/`
- **Dependencies**: Pydantic v2, FastAPI, React Error Boundary

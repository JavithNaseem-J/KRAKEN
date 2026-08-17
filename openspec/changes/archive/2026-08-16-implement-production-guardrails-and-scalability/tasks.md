## 1. Gateway Request Validation

- [x] 1.1 Define Pydantic request models (`RunQueryRequest`, `ApprovalCallbackRequest`, `KnowledgeQueryRequest`) in [`services/gateway/main.py`](file:///F:/DSML/KRAKEN/services/gateway/main.py).
- [x] 1.2 Update Gateway route handlers to use Pydantic models for incoming POST payload validation.
- [x] 1.3 Add unit tests in [`tests/unit/test_gateway.py`](file:///F:/DSML/KRAKEN/tests/unit/test_gateway.py) verifying 422 validation errors on malformed payloads.

## 2. Production Secret Assertion

- [x] 2.1 Add `validate_production_secrets()` method to `Settings` in [`shared/config.py`](file:///F:/DSML/KRAKEN/shared/config.py).
- [x] 2.2 Add unit test in [`tests/unit/test_config_validation.py`](file:///F:/DSML/KRAKEN/tests/unit/test_config_validation.py) asserting startup error when `ENVIRONMENT=prod` and default secrets are present.

## 3. Frontend Error Boundaries

- [x] 3.1 Import `ErrorBoundary` in [`frontend-react/src/App.tsx`](file:///F:/DSML/KRAKEN/frontend-react/src/App.tsx).
- [x] 3.2 Wrap `TelemetryDrawer` and `ReasoningInspectorDrawer` within `<ErrorBoundary>` tags.

## 4. Verification

- [x] 4.1 Run full unit test suite (`pytest tests/unit/`) to verify zero regressions.

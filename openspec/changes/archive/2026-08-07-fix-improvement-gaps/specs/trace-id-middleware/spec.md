## ADDED Requirements

### Requirement: Trace ID middleware extracts and binds correlation ID
A `TraceIdMiddleware` SHALL be added to all services. It SHALL extract `X-Trace-Id` (or `X-Request-Id` as fallback) from incoming request headers, generate a UUID if neither is present, bind it to `structlog.contextvars`, and add `X-Trace-Id` to the response headers.

#### Scenario: Trace ID forwarded from upstream
- **WHEN** a request arrives with `X-Trace-Id: abc-123` header
- **THEN** all structlog log entries for that request include `trace_id=abc-123` and the response includes `X-Trace-Id: abc-123`

#### Scenario: No trace ID in request
- **WHEN** a request arrives without `X-Trace-Id` or `X-Request-Id` headers
- **THEN** the middleware generates a UUID, binds it to structlog, and returns it in the `X-Trace-Id` response header

#### Scenario: Context cleared after request
- **WHEN** a request completes
- **THEN** the trace ID is unbound from structlog contextvars so it does not leak to subsequent requests

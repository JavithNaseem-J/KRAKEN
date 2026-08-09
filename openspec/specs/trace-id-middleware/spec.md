# trace-id-middleware Specification

## Purpose
Distributed request trace ID propagation across all microservices.

## Requirements

### Requirement: Trace ID middleware propagates X-Trace-Id header
`shared/middleware/trace_id.py` SHALL define a `TraceIdMiddleware` (using ASGI / BaseHTTPMiddleware) that extracts `X-Trace-Id` or `X-Request-Id` headers from incoming requests (or generates a new UUID4 string if absent), binds `trace_id` to `structlog.contextvars`, and attaches `X-Trace-Id` to all outgoing HTTP responses.

#### Scenario: Request arrives with X-Trace-Id header
- **WHEN** an HTTP request contains `X-Trace-Id: 12345`
- **THEN** all log statements emitted during that request lifecycle include `trace_id=12345`, and the response includes `X-Trace-Id: 12345`

#### Scenario: Request arrives without trace header
- **WHEN** an HTTP request contains no trace headers
- **THEN** a new UUID4 trace ID is generated, bound to `structlog`, and returned in the `X-Trace-Id` response header

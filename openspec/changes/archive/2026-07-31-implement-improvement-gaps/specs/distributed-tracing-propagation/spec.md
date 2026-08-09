## ADDED Requirements

### Requirement: Trace ID propagation in inter-service headers
`shared/http_client.py` function `service_headers(token: str | None = None, trace_id: str | None = None) -> dict[str, str]` SHALL include `"X-Trace-Id"` when `trace_id` is supplied or an existing context trace ID is present.

#### Scenario: Explicit trace_id passed
- **WHEN** `service_headers(trace_id="tr-12345")` is called
- **THEN** the returned headers dictionary contains `"X-Trace-Id": "tr-12345"`

#### Scenario: No trace_id passed
- **WHEN** `service_headers()` is called without `trace_id`
- **THEN** `"X-Service-Token"` is included and no trace header errors occur

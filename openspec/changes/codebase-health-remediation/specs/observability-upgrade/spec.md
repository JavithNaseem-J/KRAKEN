## ADDED Requirements

### Requirement: Configurable OpenTelemetry Exporter and Prometheus Metrics
The orchestrator and gateway services SHALL support configurable OpenTelemetry span export via an `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable (falling back to disabled when unconfigured, rather than printing console spans). Services SHALL expose a `/metrics` Prometheus endpoint returning HTTP request metrics, graph execution latencies, and degraded-mode gauges.

#### Scenario: OTLP exporter configured
- **WHEN** `OTEL_EXPORTER_OTLP_ENDPOINT` is set
- **THEN** OpenTelemetry spans are exported via OTLP gRPC/HTTP rather than printed to stdout

#### Scenario: Metrics endpoint scraped
- **WHEN** `GET /metrics` is requested on gateway or orchestrator
- **THEN** standard Prometheus formatted metrics are returned with HTTP 200 OK

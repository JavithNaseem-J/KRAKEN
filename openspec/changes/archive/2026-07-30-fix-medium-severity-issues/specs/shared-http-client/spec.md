## ADDED Requirements

### Requirement: Centralized Inter-Service HTTP Client Helper
The system SHALL provide a shared `create_http_client()` function and `service_headers()` helper in `shared/http_client.py` for consistent HTTP client timeouts and authentication header formatting.

#### Scenario: Inter-service Request Made
- **WHEN** an orchestrator node or service calls an internal HTTP endpoint
- **THEN** it uses the shared HTTP client helper with standardized headers and timeout parameters.

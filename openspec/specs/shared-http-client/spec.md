# shared-http-client Specification

## Purpose
TBD - created by archiving change fix-medium-severity-issues. Update Purpose after archive.
## Requirements
### Requirement: Centralized Inter-Service HTTP Client Helper
The `shared/http_client.py` module SHALL export `create_async_http_client`, `service_headers`, and `create_async_redis_client` for consistent HTTP and Redis client initialization across services.

#### Scenario: Inter-service Request Made
- **WHEN** an orchestrator node or service calls an internal HTTP endpoint or connects to Redis
- **THEN** it uses the shared client helpers from `shared.http_client` with standardized headers and timeout parameters.


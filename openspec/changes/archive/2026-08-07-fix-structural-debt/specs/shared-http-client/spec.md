## MODIFIED Requirements

### Requirement: Shared HTTP Client module exports
The `shared/http_client.py` module SHALL export `create_async_http_client`, `service_headers`, and `create_async_redis_client`.

#### Scenario: Module imports
- **WHEN** consumers import from `shared.http_client`
- **THEN** HTTP client, service headers, and Redis client factory functions are all available

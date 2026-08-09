## ADDED Requirements

### Requirement: Async HTTP client factory accepts structured timeout
The `create_async_http_client()` function in `shared/http_client.py` SHALL accept an optional `httpx.Timeout` object as a parameter, using a sensible default when omitted (`connect=5.0, read=120.0, write=10.0, pool=5.0`).

#### Scenario: Caller omits timeout
- **WHEN** a service calls `create_async_http_client()` with no arguments
- **THEN** the returned client uses the default timeout values without error

#### Scenario: Caller provides custom timeout
- **WHEN** a service calls `create_async_http_client(timeout=httpx.Timeout(connect=2.0, read=30.0, write=5.0, pool=2.0))`
- **THEN** the returned client uses the provided timeout values

### Requirement: Service-token header factory
The `shared/http_client.py` module SHALL expose a `service_headers(token: str | None = None) -> dict[str, str]` function. When `token` is `None`, it reads `get_settings().hitl_service_token`. The returned dict MUST contain `{"X-Service-Token": <token>}`.

#### Scenario: Header constructed from settings
- **WHEN** `service_headers()` is called with no argument
- **THEN** the returned dict has `X-Service-Token` equal to `get_settings().hitl_service_token`

#### Scenario: Header constructed from explicit token
- **WHEN** `service_headers(token="my-token")` is called
- **THEN** the returned dict has `X-Service-Token` equal to `"my-token"`

#### Scenario: Gateway uses factory header
- **WHEN** the gateway proxies a request to the orchestrator
- **THEN** the `X-Service-Token` header is set via `service_headers()`, not an inline dict literal

#### Scenario: Approval uses factory header
- **WHEN** the approval service calls the orchestrator callback
- **THEN** the `X-Service-Token` header is set via `service_headers()`, not an inline dict literal

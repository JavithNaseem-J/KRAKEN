# shared-redis-client-factory Specification

## Purpose
Factory function for asynchronous Redis client instantiation.

## Requirements

### Requirement: Shared Redis client factory
The system SHALL expose `create_async_redis_client(url: str)` in `shared/http_client.py`. This factory function SHALL encapsulate the instantiation of `aioredis.Redis` with consistent connection settings (`decode_responses=True`, `socket_connect_timeout=5`, `health_check_interval=15`, `retry_on_timeout=True`, `socket_keepalive=True`).

#### Scenario: Factory instantiation
- **WHEN** `create_async_redis_client(url)` is called with a valid Redis URL
- **THEN** it returns an `aioredis.Redis` client instance configured with standard options

### Requirement: Redis client factory adoption
`ShortTermMemory.__init__`, `ApprovalQueue.__init__`, and `SlidingWindowRateLimiter.__init__` SHALL use `create_async_redis_client()` instead of copy-pasting direct `aioredis.from_url` calls.

#### Scenario: Subsystems instantiate Redis client via factory
- **WHEN** `ShortTermMemory`, `ApprovalQueue`, or `SlidingWindowRateLimiter` are initialized
- **THEN** they obtain their Redis client from `create_async_redis_client()`

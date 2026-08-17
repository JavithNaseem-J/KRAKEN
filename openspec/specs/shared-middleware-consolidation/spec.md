## ADDED Requirements

### Requirement: Service Token Verification MUST Use Shared Constant-Time Security
The system SHALL route service token validation across all microservice endpoints through `shared.auth.verify_service_token` using constant-time comparison to prevent timing attacks.

#### Scenario: Valid service token provided
- **WHEN** client sends request with valid `X-Service-Token` header matching configured service secret
- **THEN** authentication dependency succeeds and passes execution to route handler.

#### Scenario: Invalid service token provided
- **WHEN** client sends request with invalid or missing `X-Service-Token` header
- **THEN** authentication dependency rejects request with `401 Unauthorized`.

### Requirement: Centralized Sliding-Window Rate Limiting Across Gateway Services
The system SHALL apply sliding-window rate limiting via `shared.middleware.rate_limit` with Redis connection pooling and localized fallback guards.

#### Scenario: Request volume within threshold
- **WHEN** incoming requests from client IP remain under rate limit threshold
- **THEN** rate limit middleware forwards request with remaining quota headers.

#### Scenario: Request volume exceeds threshold
- **WHEN** incoming request volume exceeds configured rate limit threshold
- **THEN** rate limit middleware rejects request immediately with `429 Too Many Requests`.

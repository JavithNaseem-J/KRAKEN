## MODIFIED Requirements

### Requirement: CSRF validation on approval decision submissions
The `POST /approve/{approval_id}/decision` endpoint in `services/approval/main.py` SHALL require a valid `csrf_token` matching the stored session token for `approval_id`. The `csrf_token` parameter SHALL be mandatory (`Form(...)`) and SHALL NOT be optional (`Form(None)`). CSRF tokens SHALL be single-use: verification SHALL atomically read-and-delete the stored token (e.g., Redis `GETDEL`) so that a verified token cannot be replayed within its TTL window. The CSRF verification SHALL fail-closed: if the submitted `csrf_token` is missing/empty, if the stored token is absent (never set, already consumed, or expired), or if the Redis lookup raises any exception, verification SHALL return `False` and the submission SHALL be rejected with HTTP 403. There SHALL be no "test environment" bypass or `if csrf_token is not None` guard in production code paths.

#### Scenario: Valid CSRF token submitted
- **WHEN** a decision form is submitted with a `csrf_token` matching the Redis-stored value for that `approval_id`
- **THEN** the approval decision is processed and sent to the orchestrator callback, and the CSRF token is consumed (deleted) as part of verification

#### Scenario: Invalid or missing CSRF token submitted
- **WHEN** a decision form is submitted with a missing, empty, or mismatched `csrf_token`
- **THEN** the endpoint rejects the submission with an HTTP 403 Forbidden status

#### Scenario: CSRF token replayed after successful verification
- **WHEN** a `csrf_token` that was already successfully verified is submitted a second time within its original TTL window
- **THEN** verification finds no stored token (it was consumed) and the submission SHALL be rejected with HTTP 403

#### Scenario: CSRF token missing from Redis (expired or never set)
- **WHEN** `queue.verify_csrf_token()` finds no value stored for `approval_id` in Redis
- **THEN** verification SHALL return `False` and the decision SHALL be rejected with HTTP 403

#### Scenario: Redis error during CSRF lookup
- **WHEN** a Redis exception occurs inside `queue.verify_csrf_token()`
- **THEN** verification SHALL return `False` and the decision SHALL be rejected with HTTP 403 (fail-closed, not fail-open)

## ADDED Requirements

### Requirement: Queue stats endpoint requires service token authentication
The `GET /queue/stats` endpoint in `services/approval/main.py` SHALL require a valid `X-Service-Token` header (validated via `verify_service_token`). Unauthenticated requests to `GET /queue/stats` SHALL be rejected with HTTP 403.

#### Scenario: Authenticated queue stats request
- **WHEN** an internal service calls `GET /queue/stats` with a valid `X-Service-Token`
- **THEN** the pending approval statistics are returned successfully

#### Scenario: Unauthenticated queue stats request
- **WHEN** an unauthenticated caller requests `GET /queue/stats` without `X-Service-Token`
- **THEN** the endpoint responds with HTTP 403 Forbidden

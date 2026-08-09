## MODIFIED Requirements

### Requirement: CSRF validation on approval decision submissions
The `POST /approve/{approval_id}/decision` endpoint in `services/approval/main.py` SHALL require a valid `csrf_token` matching the stored session token for `approval_id`. The CSRF verification SHALL fail-closed: if the stored token is absent (never set, already consumed, or expired) or if the Redis lookup raises any exception, verification SHALL return `False` and the submission SHALL be rejected with HTTP 403. There SHALL be no "test environment" bypass in production code paths.

#### Scenario: Valid CSRF token submitted
- **WHEN** a decision form is submitted with a `csrf_token` matching the Redis-stored value for that `approval_id`
- **THEN** the approval decision is processed and sent to the orchestrator callback

#### Scenario: Invalid or missing CSRF token submitted
- **WHEN** a decision form is submitted with a missing or mismatched `csrf_token`
- **THEN** the endpoint rejects the submission with an HTTP 403 Forbidden status

#### Scenario: CSRF token missing from Redis (expired or never set)
- **WHEN** `queue.verify_csrf_token()` finds no value stored for `approval_id` in Redis
- **THEN** verification SHALL return `False` and the decision SHALL be rejected with HTTP 403

#### Scenario: Redis error during CSRF lookup
- **WHEN** a Redis exception occurs inside `queue.verify_csrf_token()`
- **THEN** verification SHALL return `False` and the decision SHALL be rejected with HTTP 403 (fail-closed, not fail-open)

## ADDED Requirements

### Requirement: Audit history endpoints require service token authentication
The `GET /history/{session_id}` and `GET /history/user/{user_id}` endpoints in `services/audit/main.py` SHALL require a valid `X-Service-Token` header (validated via `verify_service_token`). Unauthenticated requests SHALL receive HTTP 403.

#### Scenario: Authenticated history request
- **WHEN** an internal service calls `GET /history/{session_id}` with a valid `X-Service-Token`
- **THEN** the audit records for that session are returned

#### Scenario: Unauthenticated history request
- **WHEN** an external caller requests `GET /history/{session_id}` without `X-Service-Token`
- **THEN** the endpoint responds with HTTP 403 Forbidden

### Requirement: Default service token rejected in non-dev environments
The application SHALL refuse to start if `hitl_service_token` equals the shipped default value (`"change-me-in-production"`) and the `environment` setting is not `"dev"`. A `ValueError` SHALL be raised at startup with a message instructing the operator to set a unique token.

#### Scenario: Default token in production
- **WHEN** the orchestrator starts with `HITL_SERVICE_TOKEN=change-me-in-production` and `ENVIRONMENT=prod`
- **THEN** the process raises `ValueError` and exits before accepting requests

#### Scenario: Default token in dev environment
- **WHEN** the orchestrator starts with `HITL_SERVICE_TOKEN=change-me-in-production` and `ENVIRONMENT=dev`
- **THEN** the process starts normally (dev bypass is acceptable)

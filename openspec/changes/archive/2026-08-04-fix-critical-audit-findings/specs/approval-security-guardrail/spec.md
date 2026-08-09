# approval-security-guardrail Delta Spec

## RENAMED Requirements

- FROM: `### Requirement: Default service token rejected in non-dev environments`
- TO: `### Requirement: Default or weak service token rejected unconditionally`

## MODIFIED Requirements

### Requirement: CSRF validation on approval decision submissions
The `POST /approve/{approval_id}/decision` endpoint in `services/approval/main.py` SHALL require a valid `csrf_token` matching the stored session token for `approval_id`. CSRF tokens SHALL be single-use: verification SHALL atomically read-and-delete the stored token (e.g., Redis `GETDEL`) so that a verified token cannot be replayed within its TTL window. The CSRF verification SHALL fail-closed: if the stored token is absent (never set, already consumed, or expired) or if the Redis lookup raises any exception, verification SHALL return `False` and the submission SHALL be rejected with HTTP 403. There SHALL be no "test environment" bypass in production code paths.

#### Scenario: Valid CSRF token submitted
- **WHEN** a decision form is submitted with a `csrf_token` matching the Redis-stored value for that `approval_id`
- **THEN** the approval decision is processed and sent to the orchestrator callback, and the CSRF token is consumed (deleted) as part of verification

#### Scenario: Invalid or missing CSRF token submitted
- **WHEN** a decision form is submitted with a missing or mismatched `csrf_token`
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

### Requirement: Default or weak service token rejected unconditionally
The application SHALL refuse to start if `hitl_service_token` equals the shipped default value (`"change-me-in-production"`) OR has fewer than 32 characters, in ALL environments including when `ENVIRONMENT` is unset or `"dev"`. A `ValueError` SHALL be raised at startup with a message instructing the operator to set a unique token of at least 32 characters. There SHALL be no environment-conditional bypass for weak or default tokens.

#### Scenario: Default token with production environment
- **WHEN** any service starts with `HITL_SERVICE_TOKEN=change-me-in-production` and `ENVIRONMENT=prod`
- **THEN** the process raises `ValueError` and exits before accepting requests

#### Scenario: Default token with dev or unset environment
- **WHEN** any service starts with `HITL_SERVICE_TOKEN=change-me-in-production` and `ENVIRONMENT` is `dev` or unset
- **THEN** the process raises `ValueError` and exits before accepting requests (no dev bypass)

#### Scenario: Short token rejected regardless of environment
- **WHEN** any service starts with `HITL_SERVICE_TOKEN=abc123` (fewer than 32 characters) in any environment
- **THEN** the process raises `ValueError` and exits before accepting requests

#### Scenario: Strong token accepted
- **WHEN** a service starts with a unique `HITL_SERVICE_TOKEN` of 32 or more characters
- **THEN** the settings validate successfully and the process starts normally

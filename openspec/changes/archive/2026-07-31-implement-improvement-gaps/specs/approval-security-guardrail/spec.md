## ADDED Requirements

### Requirement: CSRF validation on approval decision submissions
The `POST /approve/{approval_id}/decision` endpoint in `services/approval/main.py` SHALL require a valid `csrf_token` matching the stored session token for `approval_id`.

#### Scenario: Valid CSRF token submitted
- **WHEN** a decision form is submitted with a matching `csrf_token`
- **THEN** the approval decision is processed and sent to the orchestrator callback

#### Scenario: Invalid or missing CSRF token submitted
- **WHEN** a decision form is submitted with a missing or mismatched `csrf_token`
- **THEN** the endpoint rejects the submission with an HTTP 403 Forbidden status

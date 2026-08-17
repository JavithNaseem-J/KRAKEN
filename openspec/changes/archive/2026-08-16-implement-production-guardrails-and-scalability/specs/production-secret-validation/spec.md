## ADDED Requirements

### Requirement: Mandatory Production Environment Secret Assertion
The system SHALL validate environment configuration on startup when `ENVIRONMENT=prod` and reject execution if fallback or default development tokens are detected.

#### Scenario: Application started in production with default development secrets
- **WHEN** application boots with `ENVIRONMENT=prod` and `LLM_API_KEY` or `GATEWAY_API_KEY` set to default development values
- **THEN** configuration validator raises `ValueError` on startup preventing application initialization.

#### Scenario: Application started in production with valid custom secrets
- **WHEN** application boots with `ENVIRONMENT=prod` and all secret keys set to secure non-default values
- **THEN** configuration validation passes successfully.

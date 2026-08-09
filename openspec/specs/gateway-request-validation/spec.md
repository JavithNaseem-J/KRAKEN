# gateway-request-validation Specification

## Purpose
Strict Pydantic payload validation at the Edge API Gateway.

## Requirements

### Requirement: Gateway performs Pydantic validation on incoming requests
The `/v1/run` endpoint in `services/gateway/main.py` SHALL validate the incoming request body against `QueryRequest` (via `QueryRequest.model_validate(body)`) after parsing JSON and setting missing defaults, returning HTTP 422 Unprocessable Entity if validation fails.

#### Scenario: Missing required message field
- **WHEN** a client sends `{}` or `{"session_id": "s1"}` without a `message`
- **THEN** Gateway returns HTTP 422 with validation error details

#### Scenario: Valid request payload
- **WHEN** a client sends `{"message": "Hello"}`
- **THEN** Gateway generates `session_id` and `user_id` defaults, validates cleanly against `QueryRequest`, and proxies to orchestrator

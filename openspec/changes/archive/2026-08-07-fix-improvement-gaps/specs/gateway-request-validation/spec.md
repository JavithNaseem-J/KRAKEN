## ADDED Requirements

### Requirement: Gateway validates request body against QueryRequest model
The gateway `/v1/run` endpoint SHALL validate the parsed JSON body against `shared.models.agent.QueryRequest` using `model_validate()` before proxying to the orchestrator. On validation failure, the gateway SHALL return HTTP 422 Unprocessable Entity with Pydantic error details.

#### Scenario: Valid request passes validation
- **WHEN** a client sends a `/v1/run` request with a well-formed body matching `QueryRequest` constraints
- **THEN** the gateway proxies the request to the orchestrator normally

#### Scenario: Missing required field rejected
- **WHEN** a client sends a `/v1/run` request without a `message` field
- **THEN** the gateway returns HTTP 422 with an error detail identifying the missing field, without contacting the orchestrator

#### Scenario: Oversized message rejected
- **WHEN** a client sends a `/v1/run` request with a `message` field exceeding 4096 characters
- **THEN** the gateway returns HTTP 422 with an error detail about the field constraint violation

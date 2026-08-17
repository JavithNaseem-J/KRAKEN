## ADDED Requirements

### Requirement: Gateway Enforces Pydantic Schema Validation on Input Payloads
The Gateway service SHALL validate incoming HTTP request payloads using explicit Pydantic models before processing or forwarding requests to downstream microservices.

#### Scenario: Valid request payload sent to Gateway
- **WHEN** client submits a valid request matching `RunQueryRequest` schema to `/v1/run`
- **THEN** Gateway parses parameters successfully and forwards request downstream.

#### Scenario: Invalid request payload missing required fields
- **WHEN** client submits a request payload missing required `message` field to `/v1/run`
- **THEN** Gateway rejects request immediately with `422 Unprocessable Entity` containing field validation details.

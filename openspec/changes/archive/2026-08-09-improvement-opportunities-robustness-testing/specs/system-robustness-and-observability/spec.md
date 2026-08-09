# system-robustness-and-observability Specification

## ADDED Requirements

### Requirement: Per-Action Payload Schema Validation
The action microservice MUST validate incoming `payload` dictionaries against the action's registered `parameter_schema` before execution.

#### Scenario: Valid Payload Dispatch
- **WHEN** an `ActionRequest` is dispatched with valid parameters matching its registry schema
- **THEN** execution proceeds cleanly without throwing validation errors.

#### Scenario: Invalid Payload Rejection
- **WHEN** an `ActionRequest` is dispatched with invalid parameters violating its registry schema
- **THEN** an `ActionExecutionError` or HTTP 422 exception is raised and execution is halted.

### Requirement: JSON Approval Details Endpoint
The approval microservice MUST expose a JSON endpoint `GET /approve/{approval_id}/details` returning structured approval metadata.

#### Scenario: Fetching Approval Details via JSON
- **WHEN** the React frontend calls `GET /approve/{approval_id}/details` with a valid approval ID
- **THEN** the endpoint returns HTTP 200 OK with `action_name`, `payload`, `reasoning`, `status`, and `csrf_token` as JSON.

### Requirement: Gateway Aggregated Readiness Probe
The API Gateway MUST expose a `/ready` endpoint that checks health across all downstream microservices.

#### Scenario: All Downstream Services Healthy
- **WHEN** `/ready` is queried and orchestrator, knowledge, action, approval, memory, and audit services respond with HTTP 200 OK
- **THEN** `/ready` returns HTTP 200 OK with `"status": "ready"`.

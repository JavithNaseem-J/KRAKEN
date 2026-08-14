## ADDED Requirements

### Requirement: Prompt injection attempts are blocked at the Gateway
The system SHALL classify incoming user messages in the Gateway pre-flight middleware and reject requests that match known prompt injection patterns before they reach the orchestrator.

#### Scenario: Direct instruction override is blocked
- **WHEN** a request body contains patterns like "ignore all previous instructions" or "disregard your system prompt"
- **THEN** the Gateway returns HTTP 400 with `{"error": "Request blocked: potential prompt injection detected."}`

#### Scenario: Legitimate security query is not blocked
- **WHEN** a user asks "What is the SLA for critical vulnerabilities?"
- **THEN** the request passes through the middleware unmodified

#### Scenario: Operator header bypasses injection check
- **WHEN** a request carries `X-Operator-Role: operator` and matches an injection pattern
- **THEN** the request is allowed through and the pattern match is logged as a warning (not blocked)

#### Scenario: Blocked attempts are logged
- **WHEN** a request is blocked by the injection guard
- **THEN** a structured log entry is emitted with the matched pattern, truncated query text, and request ID

# sse-hitl-handshake-remediation Specification

## Purpose
Specification for sse-hitl-handshake-remediation.

## Requirements

### Requirement: SSE Stream MUST Yield Pending Approval Payload on Graph Interrupt
When the LangGraph execution pauses at a HITL interrupt during streaming, the system SHALL register the approval record and yield an SSE data event containing the `pending_approval` response payload before closing the stream.

#### Scenario: Stream interrupted by critical action
- **WHEN** agent graph execution hits a HITL interrupt during SSE streaming
- **THEN** orchestrator registers the approval ID and yields an SSE payload with `status: "pending_approval"`, `approval_id`, and `message`.

### Requirement: Ticket ID Mandate for Write Actions
The system SHALL NOT permit `escalate`, `request_info`, or `close` actions unless an explicit ticket ID (matching regex pattern `(TCK|T|TK|INC|SR)[-_]?\d+`) is present in the prompt or state.

#### Scenario: Prompt without explicit ticket ID
- **WHEN** user submits "What is the SLA for critical security vulnerabilities?" (containing words like "critical" or "vulnerabilities" but no ticket ID)
- **THEN** decider node overrides action to `auto_respond` (SAFE).

### Requirement: Clean Frontend Stream Handling
The frontend SHALL NOT append duplicate plain-text messages when an SSE stream finishes, and SHALL render pending approval cards only when a valid `approval_id` is present.

#### Scenario: Stream returns pending approval response
- **WHEN** frontend receives a streaming completion payload with `status: "pending_approval"`
- **THEN** frontend appends a single message card with `approval_id` and sets approval state to `pending`.

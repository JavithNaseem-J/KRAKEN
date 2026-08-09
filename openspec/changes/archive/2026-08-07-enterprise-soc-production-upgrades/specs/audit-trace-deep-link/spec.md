# audit-trace-deep-link Specification

## ADDED Requirements

### Requirement: Audit Service Trace Deep Link
The system MUST render a direct link button in the Reasoning Inspector drawer leading to the Audit Microservice event log for the active trace ID.

#### Scenario: Inspecting trace in Audit Service
- **WHEN** the user opens the Reasoning Inspector drawer for a message with a trace ID
- **THEN** an external link button to `http://localhost:8006/audit/events/{trace_id}` is rendered.

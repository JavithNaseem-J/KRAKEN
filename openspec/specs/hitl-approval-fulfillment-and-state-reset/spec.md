# hitl-approval-fulfillment-and-state-reset Specification

## Purpose
Specification for hitl-approval-fulfillment-and-state-reset.

## Requirements

### Requirement: HITL Approval Fulfillment & Text Generation Confirmation
When a human operator grants approval for an action (`approval_status == 'approved'`) and the action service executes successfully (`action_result` indicates `success: true`), `responder_node` SHALL output a confirmation response detailing the action results (including created ticket IDs) and SHALL NOT produce a refusal or denial response.

#### Scenario: Approved Ticket Creation Returns Success Response
- **WHEN** human approval is submitted for `create_ticket` and `action_result` contains `{"success": true, "ticket_id": "TCK-1006"}`
- **THEN** the system SHALL output a confirmation response indicating ticket `TCK-1006` was created successfully.

### Requirement: Session Thread State Reset After HITL Completion
When a new query is submitted on a session thread that previously completed or resolved an approval interrupt, the orchestrator SHALL clear residual interrupt state (`snapshot.next`) so the new query executes cleanly without prompting for human approval again.

#### Scenario: Subsequent Query Executes Cleanly After HITL Resolution
- **WHEN** a user submits a new query (e.g., "How do I connect to the corporate VPN?") after an approval card is resolved
- **THEN** the system SHALL process the query directly via `auto_respond` without returning "A CRITICAL triage action requires human approval".

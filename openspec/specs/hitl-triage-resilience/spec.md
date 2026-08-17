# hitl-triage-resilience Specification

## Purpose
Specification for HITL triage resilience, routing, state isolation, approval cards, and telemetry interaction.

## Requirements

### Requirement: Informational Ticket Status Queries MUST Route to Auto Respond
The system SHALL route all informational, how-to, FAQ, and status queries regarding tickets or policy to `auto_respond` without triggering human-in-the-loop (HITL) approval gates.

#### Scenario: User queries ticket status
- **WHEN** user submits "What is the status of ticket T-1001?"
- **THEN** decider selects `auto_respond` action and responder returns informational details without firing HITL approval.

### Requirement: Thread Execution State Isolation Across User Queries
The system SHALL reset or isolate execution state when a new user query arrives on a session thread that was previously interrupted, preventing stale responder execution from previous queries.

#### Scenario: New query after interrupted session
- **WHEN** user submits "How do I connect to the corporate VPN?" on a session that previously hit a HITL gate
- **THEN** orchestrator processes the VPN query cleanly and returns the VPN response without executing responder on previous query state.

### Requirement: Approval Details Sync and Resilient UI Card Rendering
The system SHALL synchronize pending approval records with the Approval Service (port 8004) and render `Authorize Execution` / `Deny Request` buttons on pending approval cards without premature expiration errors.

#### Scenario: Approval details loaded in UI
- **WHEN** frontend renders an inline approval card for pending approval ID
- **THEN** approval details are fetched successfully from Approval Service and active action buttons are displayed.

### Requirement: Scoped Telemetry Inspection Interaction
The UI SHALL open the Telemetry Inspector drawer ONLY when the user explicitly clicks the Telemetry badge button, and NOT on generic message bubble clicks.

#### Scenario: Explicit telemetry button click
- **WHEN** user clicks the Telemetry button badge under an assistant message
- **THEN** Telemetry Inspector drawer opens, while clicking on message text does not open the drawer.

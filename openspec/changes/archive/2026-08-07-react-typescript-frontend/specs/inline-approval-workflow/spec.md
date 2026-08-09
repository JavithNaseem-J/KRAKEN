# inline-approval-workflow Specification

## ADDED Requirements

### Requirement: Embedded Approval Cards
The system MUST render inline Approval Cards directly within the chat message stream when an action status is `pending_approval`.

#### Scenario: Rendering pending approval card
- **WHEN** an action requires HITL approval
- **THEN** an inline approval card is displayed showing requested action name, risk level badge, reasoning summary, and `✓ Approve` / `✕ Reject` controls

### Requirement: Direct Approval Decision Submission
The system MUST submit approval decisions directly to the Approval Service (`POST /approve/{approval_id}/decision`).

#### Scenario: User approves action in chat
- **WHEN** the user clicks `✓ Approve` on the inline card
- **THEN** the app submits the decision and auto-poller updates the chat message with the executed response

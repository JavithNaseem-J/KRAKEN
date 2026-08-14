# editable-hitl-card Specification

## Purpose
TBD - created by archiving change kraken-production-polish. Update Purpose after archive.
## Requirements
### Requirement: Ticket creation HITL card renders pre-filled editable fields
The system SHALL, when a `create_ticket` action enters the HITL approval queue, serialize LLM-extracted ticket fields into the approval payload, and the `InlineApprovalCard` SHALL render those fields as editable inputs the analyst can correct before approving.

#### Scenario: Natural language ticket request populates HITL form
- **WHEN** the user types "Create an IT ticket for Alice's broken monitor"
- **THEN** the HITL approval card appears with pre-filled fields: `affected_user: Alice`, `category: Hardware`, `priority: Medium`, `description: Monitor malfunction reported by user`

#### Scenario: Analyst corrects a pre-filled field before approving
- **WHEN** the analyst changes the priority from "Medium" to "High" in the editable HITL card
- **THEN** the corrected value is submitted with the approval decision and the ticket is created with `priority: High`

#### Scenario: Approval creates ticket in database with extracted fields
- **WHEN** the analyst clicks "Approve" on the pre-filled HITL card
- **THEN** the ticket is created with all edited field values and a confirmation message shows the new ticket ID (e.g., `TCK-1012`)


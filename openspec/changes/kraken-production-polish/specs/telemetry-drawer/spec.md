## ADDED Requirements

### Requirement: Assistant messages expose a telemetry drawer on click
The system SHALL render a collapsible telemetry drawer when the user clicks any assistant chat message, displaying RBAC clearance role, retrieved chunk relevance scores, trace ID, and execution duration.

#### Scenario: User opens telemetry drawer
- **WHEN** the user clicks an assistant message
- **THEN** a slide-in panel appears showing: active persona role, top-3 chunk relevance scores, trace ID, and total execution time in milliseconds

#### Scenario: Missing telemetry fields render gracefully
- **WHEN** the backend response does not include chunk scores or trace ID
- **THEN** those fields display "N/A" — the drawer still opens without error

#### Scenario: Drawer closes on second click or Escape key
- **WHEN** the user clicks the message again or presses Escape
- **THEN** the drawer slides out and the message returns to its normal state

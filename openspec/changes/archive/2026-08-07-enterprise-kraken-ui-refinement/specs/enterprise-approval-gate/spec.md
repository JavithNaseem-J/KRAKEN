# enterprise-approval-gate Specification

## ADDED Requirements

### Requirement: Enterprise Security Gate Alert Card
The system MUST render Human-in-the-Loop approval requests in a high-contrast enterprise alert card featuring a left border accent, metadata grid, and clear decision buttons.

#### Scenario: Rendering approval gate
- **WHEN** an autonomous execution requires human authorization
- **THEN** the approval card displays action name, risk level, formatted justification prose, and high-contrast `Approve & Execute` / `Deny Request` controls.

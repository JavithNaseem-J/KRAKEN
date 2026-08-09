# dynamic-header-approval-status-badge Specification

## ADDED Requirements

### Requirement: Dynamic Header Authorization Lifecycle Status
The system MUST dynamically update the top-right header status badge to reflect whether an authorization request is awaiting user decision or currently executing after approval.

#### Scenario: Awaiting user approval
- **WHEN** an approval request is pending user action
- **THEN** the top-right header renders `Awaiting Security Authorization…` (Amber badge).

#### Scenario: Approved and executing
- **WHEN** the user approves an action and background execution is active
- **THEN** the top-right header renders `Executing Authorized Action…` (Emerald badge with spinner).

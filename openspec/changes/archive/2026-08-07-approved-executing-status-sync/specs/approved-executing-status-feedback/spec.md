# approved-executing-status-feedback Specification

## ADDED Requirements

### Requirement: Approved Executing vs Executed Status Synchronization
The system MUST display `APPROVED & EXECUTING…` while action execution is actively running, and `APPROVED & EXECUTED` only after execution has completed.

#### Scenario: User approves action and execution starts
- **WHEN** the user approves an action and background execution is active
- **THEN** the card and timestamp status display `APPROVED & EXECUTING…` with a spinner.

#### Scenario: Execution completes
- **WHEN** background execution returns its result
- **THEN** the card and timestamp status update to `APPROVED & EXECUTED` with a check icon.

# approval-404-graceful-expiration Specification

## ADDED Requirements

### Requirement: Graceful 404 Expiration Handling
The system MUST handle HTTP 404 errors when fetching approval details as expired authorization requests, locking the card without displaying raw HTTP error alerts.

#### Scenario: 404 Error on Detail Fetch
- **WHEN** `fetchApprovalDetails` receives an HTTP 404 error
- **THEN** the approval card transitions to `🔒 AUTHORIZATION EXPIRED` state and raw HTTP error alerts are suppressed.

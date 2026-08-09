# approval-poller-error-resilience Specification

## ADDED Requirements

### Requirement: Execution Polling Safety Timeouts and Error Limits
The system MUST limit post-approval background polling to a maximum of 2 minutes or 5 consecutive network errors to prevent indefinite UI hangs.

#### Scenario: Network disconnect during execution polling
- **WHEN** 5 consecutive poll requests fail due to network or server errors
- **THEN** the system stops polling, clears the pending session state, and appends a disconnect system alert.

#### Scenario: Post-approval execution timeout
- **WHEN** action execution polling exceeds 2 minutes without a final response
- **THEN** the system stops polling, clears the pending session state, and appends an execution timeout system alert.

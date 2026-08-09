# approval-timeout-autoclose Specification

## ADDED Requirements

### Requirement: Locked Expired Approval State
The system MUST auto-close expired approval cards, disabling decision buttons and rendering status `🔒 AUTHORIZATION EXPIRED`.

#### Scenario: Approval Timeout Expiration
- **WHEN** an approval countdown expires or poller receives timeout
- **THEN** decision buttons are disabled and status displays `🔒 AUTHORIZATION EXPIRED`.

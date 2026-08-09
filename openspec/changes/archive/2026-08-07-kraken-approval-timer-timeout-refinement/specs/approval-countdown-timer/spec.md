# approval-countdown-timer Specification

## ADDED Requirements

### Requirement: Live Remaining Time Countdown
The system MUST display a live countdown timer (`Expires in MM:SS`) for pending approval requests.

#### Scenario: Active approval countdown
- **WHEN** an approval card is pending authorization
- **THEN** a live countdown timer updates every second showing remaining time before expiration.

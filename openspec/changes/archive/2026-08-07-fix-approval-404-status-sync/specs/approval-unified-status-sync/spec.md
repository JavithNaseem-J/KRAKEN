# approval-unified-status-sync Specification

## ADDED Requirements

### Requirement: Unified Approval Status Sync
The system MUST synchronize the approval status between the Inline Approval Card and the timestamp status badge below the card.

#### Scenario: Expired Card Status Sync
- **WHEN** an approval card is in an expired state
- **THEN** both the card status and the timestamp line render `🔒 AUTHORIZATION EXPIRED`.

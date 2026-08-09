# streamlined-approval-card-metadata Specification

## ADDED Requirements

### Requirement: Truncated Approval Reference Badge
The system MUST display truncated Approval Reference IDs with a copy action, omitting static protocol labels.

#### Scenario: Rendering approval card footer
- **WHEN** an approval card footer renders
- **THEN** it displays a truncated reference badge (e.g. `Ref: #7ff3c0c2`) with copy support and does not display static protocol strings.

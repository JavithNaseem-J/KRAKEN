# clean-header-session-title Specification

## ADDED Requirements

### Requirement: Human-Readable Session Header Title
The system MUST display the human-readable Session Title in the top header bar instead of raw session UUID strings.

#### Scenario: Rendering top header bar
- **WHEN** the chat header renders
- **THEN** it displays the active session's title (or "New Session" fallback) rather than a raw UUID string.

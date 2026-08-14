## ADDED Requirements

### Requirement: Session sidebar displays auto-generated titles and relative timestamps
The system SHALL auto-generate a session title from the first 50 characters of the first user message in that session (truncated with ellipsis if longer) and SHALL display relative timestamps (e.g., "2 hours ago", "Yesterday") in the sidebar session list.

#### Scenario: New session gets auto-titled on first message
- **WHEN** the user sends the first message in a new session
- **THEN** the session title in the sidebar updates to the first 50 characters of that message

#### Scenario: Relative timestamps shown in sidebar
- **WHEN** the sidebar renders a list of sessions
- **THEN** each session shows a relative timestamp based on `updated_at` (e.g., "just now", "3 hours ago", "Aug 13")

## ADDED Requirements

### Requirement: All runtime errors surface as structured chat cards, never raw stack traces
The system SHALL wrap the React application in an `ErrorBoundary` component. Any unhandled React error SHALL render a friendly error card in the chat UI with an incident ID. Backend 4xx and 5xx responses from the API SHALL be caught and rendered as structured error messages, not raw Axios error strings.

#### Scenario: Unhandled React error triggers error boundary
- **WHEN** a React component throws an unhandled exception
- **THEN** a friendly card appears: "KRAKEN encountered an unexpected issue. Incident ID: #abc123." — no stack trace is visible to the user

#### Scenario: Backend 500 error renders as structured chat message
- **WHEN** the API returns HTTP 500
- **THEN** the chat displays: "The agent encountered an error processing your request. Please try again." — the raw error message is NOT shown

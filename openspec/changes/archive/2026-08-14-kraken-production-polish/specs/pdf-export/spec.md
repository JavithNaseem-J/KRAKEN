## ADDED Requirements

### Requirement: Sessions can be exported as executive incident briefing PDFs
The system SHALL expose `POST /v1/report/export` that accepts a `session_id` and returns a downloadable PDF containing the session messages, ticket actions taken, analyst persona, and a timestamp header.

#### Scenario: User exports a completed session
- **WHEN** the user clicks "Export PDF" on a session with at least one assistant response
- **THEN** the browser downloads a PDF file named `kraken-incident-{session_id[:8]}.pdf`

#### Scenario: Export includes all session messages
- **WHEN** the PDF is generated
- **THEN** it SHALL contain: session ID, export timestamp, persona name and role, all user and assistant messages in order, and any ticket IDs created during the session

#### Scenario: Empty session export is rejected
- **WHEN** the `session_id` has no messages
- **THEN** the endpoint returns HTTP 400 with `{"error": "Session has no messages to export"}`

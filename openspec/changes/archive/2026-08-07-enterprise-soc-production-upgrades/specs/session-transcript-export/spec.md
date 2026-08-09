# session-transcript-export Specification

## ADDED Requirements

### Requirement: Session Audit Log Export
The system MUST provide a button in the main window header allowing users to download the session audit transcript as a JSON file.

#### Scenario: Exporting session audit log
- **WHEN** the user clicks the Export Audit Log button in the header bar
- **THEN** a formatted JSON file containing session messages, timestamps, and reasoning traces is downloaded.

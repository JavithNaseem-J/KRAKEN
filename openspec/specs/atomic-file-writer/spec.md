# atomic-file-writer Specification

## Purpose
TBD - created by archiving change fix-medium-severity-issues. Update Purpose after archive.
## Requirements
### Requirement: Atomic JSON File Persistence
The system SHALL provide `atomic_write_json(path, data)` in `shared/path_validator.py` to write temporary files and atomically replace target files to prevent partial writes.

#### Scenario: Ticket or File Action Update
- **WHEN** the action service writes or updates a JSON file inside the workspace
- **THEN** it uses `atomic_write_json` to perform a safe temporary file creation and atomic replacement.


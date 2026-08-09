## ADDED Requirements

### Requirement: Unified Registry Action Handler Dispatch
The system SHALL bind execution handlers directly to action definitions in `shared/registry.py` or dispatch dynamically via registry metadata in `services/action/main.py`.

#### Scenario: Action Request Execution
- **WHEN** the Action service receives an `/execute` request
- **THEN** it looks up the action handler in the registry mapping and dispatches without manual `if/elif` branching.

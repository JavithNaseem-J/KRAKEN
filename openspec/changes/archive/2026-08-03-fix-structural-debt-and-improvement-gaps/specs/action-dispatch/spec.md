## MODIFIED Requirements

### Requirement: Unified Registry Action Handler Dispatch
The system SHALL bind execution handlers directly to action definitions in `shared/registry.py` or dispatch dynamically via registry metadata in `services/action/main.py`. Ticket mutation actions (escalate, request_info, close) SHALL share a common `_mutate_ticket(ticket_id, new_status, extra_fields)` helper that encapsulates the lock/load/find/mutate/save/log pattern. Public handler functions SHALL be thin wrappers performing only argument validation before delegating to the helper. The ticket file lock SHALL be a process-local `threading.Lock` (not a Redis distributed lock), since the ticket JSON file is local to this service's filesystem.

#### Scenario: Action Request Execution
- **WHEN** the Action service receives an `/execute` request
- **THEN** it looks up the action handler in the registry mapping and dispatches without manual `if/elif` branching

#### Scenario: Ticket mutation uses shared helper
- **WHEN** any of escalate, request_info, or close executes against a ticket
- **THEN** the mutation (lock acquisition, file load, ticket lookup, field update, save, log) is performed once via `_mutate_ticket` with action-specific `extra_fields`

#### Scenario: Ticket lock is process-local
- **WHEN** two concurrent ticket-mutation requests arrive
- **THEN** they are serialised by a `threading.Lock` (not a Redis lock); no Redis connection is required for ticket operations

#### Scenario: Escalate maintains result contract
- **WHEN** `execute_escalate` completes successfully
- **THEN** it returns a result dict with `ticket_id`, `status_updated_to`, `priority`, `reason`, `evidence_cited`, and `success: True`

## ADDED Requirements

### Requirement: Action service image does not include unused asyncpg dependency
The `services/action/requirements.txt` SHALL NOT include `asyncpg`. The action service does not connect to PostgreSQL directly.

#### Scenario: Action service image build
- **WHEN** the action service Docker image is built
- **THEN** `asyncpg` is not installed in the image (verified by `pip show asyncpg` returning non-zero in the container)

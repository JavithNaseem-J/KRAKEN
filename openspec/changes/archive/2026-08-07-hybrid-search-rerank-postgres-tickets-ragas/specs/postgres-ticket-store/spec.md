# postgres-ticket-store Specification

## ADDED Requirements

### Requirement: PostgreSQL-backed ticket repository
The Action Service (`services/action/`) SHALL maintain a `tickets` table in PostgreSQL containing columns `ticket_id` (PRIMARY KEY), `title`, `description`, `status`, `priority`, `created_at`, `updated_at`, and `payload` (JSONB).

#### Scenario: Database schema initialization
- **WHEN** the Action Service starts up with a valid `postgres_sync_url`
- **THEN** it SHALL execute `CREATE TABLE IF NOT EXISTS tickets (...)` and ensure required indexes are present

#### Scenario: Atomic ticket mutation with row-level locking
- **WHEN** any ticket action (`auto_respond`, `escalate`, `request_info`, `close`) executes
- **THEN** it SHALL acquire a row-level lock (`SELECT ... FOR UPDATE`), update status and extra fields atomically in PostgreSQL, and commit the transaction

#### Scenario: Fallback to local JSON file
- **WHEN** PostgreSQL connection is unavailable or unconfigured (e.g. offline unit testing)
- **THEN** ticket handlers SHALL fall back to local `./data/workspace/tickets.json` file operations

# shared-ticket-db-helpers Specification

## Purpose
Shared PostgreSQL ticket table DDL and seeding helpers.

## Requirements

### Requirement: Shared ticket table DDL
The system SHALL define the PostgreSQL `tickets` table DDL in exactly one location: `shared/db/tickets.py::ensure_tickets_table(conn)`. All other code that needs the table to exist SHALL call this function rather than inlining `CREATE TABLE` SQL.

#### Scenario: Table created on first use
- **WHEN** `ensure_tickets_table(conn)` is called against a database with no `tickets` table
- **THEN** the `tickets` table is created with columns `id`, `title`, `status`, `priority`, `payload`, `updated_at`

#### Scenario: Idempotent on subsequent calls
- **WHEN** `ensure_tickets_table(conn)` is called against a database where `tickets` already exists
- **THEN** no error is raised and the table structure is unchanged

### Requirement: Shared ticket seeding
The system SHALL expose `seed_tickets(conn, data: list[dict])` in `shared/db/tickets.py`. This function SHALL perform `INSERT ... ON CONFLICT (id) DO UPDATE` so seeds are idempotent.

#### Scenario: Seed inserts new rows
- **WHEN** `seed_tickets(conn, data)` is called with tickets whose IDs do not yet exist
- **THEN** each ticket is inserted into the `tickets` table

#### Scenario: Seed updates existing rows
- **WHEN** `seed_tickets(conn, data)` is called with tickets whose IDs already exist
- **THEN** the existing rows are updated with the new `title`, `status`, and `payload` values

### Requirement: Consumer delegation
`ticket_handler.py::_init_pg_tickets_table()` and `scripts/seed_data.py::seed_postgres()` SHALL each delegate to `shared/db/tickets.py` rather than containing inline DDL or seeding SQL.

#### Scenario: ticket_handler uses shared DDL
- **WHEN** the action service starts and initialises the ticket pool
- **THEN** `_init_pg_tickets_table()` calls `ensure_tickets_table()` from `shared/db/tickets.py` with no inline DDL

#### Scenario: seed_data script uses shared seed function
- **WHEN** `scripts/seed_data.py` is run
- **THEN** it calls `seed_tickets()` from `shared/db/tickets.py` with no inline INSERT SQL

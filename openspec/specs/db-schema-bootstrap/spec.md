# db-schema-bootstrap Specification

## Purpose
TBD - created by archiving change codebase-health-remediation. Update Purpose after archive.
## Requirements
### Requirement: Idempotent Database Schema Bootstrap
Services requiring database tables (`audit`, `memory`, `action`) SHALL execute an idempotent schema bootstrap helper `ensure_schema()` during FastAPI `lifespan()` startup whenever `postgres_url` is non-empty. `ensure_schema()` SHALL execute DDL statements creating `audit_log`, `episodic_memory`, `tickets` tables, and associated `pgvector` indexes if they do not already exist.

#### Scenario: Startup against empty PostgreSQL database
- **WHEN** a service starts up with a valid `POSTGRES_URL` against a newly initialized database
- **THEN** `ensure_schema()` executes `CREATE TABLE IF NOT EXISTS` and vector index creation without error before servicing requests

#### Scenario: Startup against existing populated database
- **WHEN** a service starts up and tables already exist
- **THEN** `ensure_schema()` executes idempotently without modifying existing records or failing


# Orchestrator Service Capability Specification

## Requirements

### Requirement: TCP Keep-Alive Connection Pool Recycling
The Orchestrator checkpointer service SHALL initialize PostgreSQL connection pools with OS-level TCP keep-alives and maximum idle connection lifetimes to prevent dropped sockets during background polling loops.

#### Scenario: Idle connection health
- **WHEN** a background worker or polling loop stays idle for more than 30 seconds
- **THEN** TCP keep-alive packets maintain the socket connection to Supabase PgBouncer pooler without dropping connections

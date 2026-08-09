## ADDED Requirements

### Requirement: Orchestrator graceful shutdown drains graph semaphore
`services/orchestrator/main.py` SHALL handle lifespan shutdown by flagging startup state to reject new `/run` requests with HTTP 503 and acquiring all `graph_semaphore` slots up to `max_concurrency` before closing DB pools and HTTP clients.

#### Scenario: Graceful shutdown with in-flight graph execution
- **WHEN** the orchestrator process receives SIGTERM while graph runs are executing
- **THEN** new incoming requests are rejected with 503 while in-flight executions finish releasing their semaphore slots before process exit

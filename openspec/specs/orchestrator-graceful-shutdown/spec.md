# orchestrator-graceful-shutdown Specification

## Purpose
Graceful shutdown and task draining in the LangGraph Orchestrator service.

## Requirements

### Requirement: Orchestrator drains in-flight graph tasks on shutdown
During lifespan shutdown in `services/orchestrator/main.py`, the service SHALL set `app.state.is_shutting_down = True` and acquire all `settings.orchestrator_max_concurrency` semaphore slots with a timeout (5.0s per slot) to allow in-flight graph executions to complete cleanly before closing database pools and HTTP clients.

#### Scenario: Service receives SIGTERM during active graph execution
- **WHEN** SIGTERM is received while an agent graph run is in progress
- **THEN** new incoming requests are rejected with HTTP 503 ("Server shutting down."), and shutdown waits for active graph runs to acquire semaphore slots before tearing down state

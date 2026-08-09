# orchestrator-concurrency-control Delta Spec

## ADDED Requirements

### Requirement: Approval callback resumptions use the bounded executor and semaphore
The `POST /approval-callback` endpoint in `services/orchestrator/main.py` SHALL resume paused graphs through the same bounded `graph_executor` and `graph_semaphore` used by `POST /run`. It SHALL NOT use `run_in_executor(None, ...)` (the unbounded default executor). Semaphore acquisition SHALL use the atomic `asyncio.wait_for(semaphore.acquire(), timeout=0.0)` pattern and return HTTP 503 when no slot is available. The Postgres idempotency transaction (`SELECT FOR UPDATE` + status update) SHALL complete before semaphore acquisition, so a capacity-related 503 leaves the approval in `pending` status and retryable by the caller.

#### Scenario: Callback resumes within capacity
- **WHEN** an approval callback arrives and a semaphore slot is available
- **THEN** the graph resumption executes on the bounded `graph_executor` and the semaphore slot is released when finished

#### Scenario: Callback rejected at concurrency limit
- **WHEN** an approval callback arrives while all semaphore slots are in use
- **THEN** the endpoint returns HTTP 503 Service Unavailable and the approval record remains in `pending` status (the idempotency update was not committed as resolved)

#### Scenario: Callback never uses the default executor
- **WHEN** any graph resumption is triggered by `/approval-callback`
- **THEN** it runs on `app.state.graph_executor` (bounded), never on Python's unbounded default `ThreadPoolExecutor`

### Requirement: Graph node retries do not block worker pool threads
Retry logic inside agent graph nodes (`retriever_node`, `executor_node`) SHALL NOT use `time.sleep()` or any other thread-blocking wait. Nodes SHALL perform retries with non-blocking waits (e.g., `asyncio.sleep()` via an async retry library such as `tenacity` with async support) and SHALL use async HTTP clients, so that a downstream outage cannot exhaust the bounded worker pool by stalling threads. The existing retry budget (3 attempts with backoff) and the existing failure behavior (graceful error state, e.g., "Knowledge retrieval is temporarily unavailable") SHALL be preserved.

#### Scenario: Downstream service hiccup during concurrent requests
- **WHEN** the knowledge service fails transiently while multiple graph executions are in flight
- **THEN** retry waits yield control (async sleep) instead of blocking worker threads, and no thread in the bounded pool is stalled for the duration of a backoff

#### Scenario: Retries exhausted
- **WHEN** all retry attempts against the knowledge service fail
- **THEN** the node returns the same graceful error result as before (empty chunks plus an error message), with no change in external behavior

#### Scenario: No blocking sleep in node code
- **WHEN** the retriever and executor node modules are inspected
- **THEN** neither module calls `time.sleep()` in its request/retry path

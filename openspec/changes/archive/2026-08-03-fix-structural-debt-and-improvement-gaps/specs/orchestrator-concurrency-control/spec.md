## MODIFIED Requirements

### Requirement: Bounded worker pool and concurrency limit for agent graph
`services/orchestrator/main.py` SHALL execute `agent_graph.invoke` using a bounded `ThreadPoolExecutor` and limit concurrent graph runs using an `asyncio.Semaphore`. The semaphore slot acquisition SHALL be atomic: the system SHALL use `asyncio.wait_for(semaphore.acquire(), timeout=0.0)` to detect a full semaphore without a TOCTOU race. A pre-check via `semaphore.locked()` SHALL NOT be used. The semaphore size and worker count SHALL be configurable via environment variables (`ORCHESTRATOR_MAX_CONCURRENCY`, `ORCHESTRATOR_WORKERS`) with defaults of 5 and 4 respectively.

#### Scenario: Capacity available
- **WHEN** a `/run` request arrives and active graph executions are below the concurrency limit
- **THEN** the request atomically acquires the semaphore slot and executes on the worker thread pool

#### Scenario: Concurrency limit reached
- **WHEN** a `/run` request arrives when all semaphore slots are in use
- **THEN** the server immediately returns HTTP 503 Service Unavailable with a busy message; no race condition allows the 6th request through

#### Scenario: Semaphore acquisition is atomic
- **WHEN** exactly `max_concurrency` requests are in flight simultaneously
- **THEN** any additional concurrent request receives HTTP 503 (not a sporadic pass-through due to a TOCTOU window)

#### Scenario: Concurrency limit is env-configurable
- **WHEN** `ORCHESTRATOR_MAX_CONCURRENCY=10` is set in the environment
- **THEN** the orchestrator allows up to 10 concurrent graph executions before returning 503

## ADDED Requirements

### Requirement: Stale checkpoint pruning covers checkpoint_writes table
The `prune_stale_checkpoints()` function in `services/orchestrator/main.py` SHALL delete rows from both the `checkpoints` table AND the `checkpoint_writes` table for the same set of stale `thread_id` values. The `deleted_counts` return dict SHALL accurately report the number of rows deleted from each table.

#### Scenario: Checkpoint pruning clears both tables
- **WHEN** `prune_stale_checkpoints()` runs and finds stale checkpoint entries
- **THEN** corresponding rows are deleted from both `checkpoints` and `checkpoint_writes`, and the returned `deleted_counts["checkpoint_writes"]` is greater than zero

#### Scenario: No stale checkpoints
- **WHEN** `prune_stale_checkpoints()` runs and no stale entries exist
- **THEN** both deletion queries execute with zero rows affected and both counters are 0

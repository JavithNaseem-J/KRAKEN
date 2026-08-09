## MODIFIED Requirements

### Requirement: Graph node retries do not block worker pool threads
Retry logic inside agent graph nodes (`retriever_node`, `executor_node`) SHALL NOT use `time.sleep()` or any other thread-blocking wait. Nodes SHALL perform retries with non-blocking waits (e.g., `asyncio.sleep()` via an async retry library such as `tenacity` with async support) and SHALL use async HTTP clients (`AsyncQdrantClient`, `httpx.AsyncClient`), so that a downstream outage or database call cannot stall the event loop thread. All LLM invocations in graph nodes (`decider_node`, `reasoner_node`, `responder_node`) SHALL use asynchronous `await llm.ainvoke()` instead of synchronous `llm.invoke()`. The existing retry budget (3 attempts with backoff) and the existing failure behavior (graceful error state) SHALL be preserved.

#### Scenario: Downstream service hiccup during concurrent requests
- **WHEN** the knowledge service fails transiently while multiple graph executions are in flight
- **THEN** retry waits yield control (async sleep) instead of blocking threads, and no event loop thread is stalled for the duration of a backoff

#### Scenario: Retries exhausted
- **WHEN** all retry attempts against the knowledge service fail
- **THEN** the node returns the same graceful error result as before (empty chunks plus an error message), with no change in external behavior

#### Scenario: No blocking sleep or sync LLM calls in node code
- **WHEN** graph nodes are executed under load
- **THEN** node execution yields asynchronously on all LLM calls and Qdrant/HTTP requests, maintaining event loop responsiveness

### Requirement: Stale checkpoint pruning covers checkpoint_writes table
The `prune_stale_checkpoints()` function in `services/orchestrator/main.py` SHALL delete rows from both the `checkpoints` table AND the `checkpoint_writes` table for the same set of stale `thread_id` values. All SQL queries executed during pruning SHALL use parameterized CTEs and SHALL NOT use f-string query string formatting. The `deleted_counts` return dict SHALL accurately report the number of rows deleted from each table.

#### Scenario: Checkpoint pruning clears both tables
- **WHEN** `prune_stale_checkpoints()` runs and finds stale checkpoint entries
- **THEN** corresponding rows are deleted from both `checkpoints` and `checkpoint_writes`, and the returned `deleted_counts["checkpoint_writes"]` is greater than zero

#### Scenario: No stale checkpoints
- **WHEN** `prune_stale_checkpoints()` runs and no stale entries exist
- **THEN** both deletion queries execute with zero rows affected and both counters are 0

#### Scenario: Parameterized query execution
- **WHEN** `prune_stale_checkpoints()` is invoked
- **THEN** SQL statements are prepared and executed using DB-API query parameters rather than Python string formatting

## ADDED Requirements

### Requirement: Memory writer uses non-blocking async execution
The `memory_writer_node` SHALL perform background message appending and long-term memory storing using non-blocking async HTTP tasks (`asyncio.create_task` with `app.state.http`). It SHALL NOT create a standalone module-level synchronous HTTP client or thread pool.

#### Scenario: Memory writing on graph completion
- **WHEN** the `memory_writer_node` executes at the end of a graph run
- **THEN** memory persistence tasks are scheduled asynchronously without spawning additional thread pools

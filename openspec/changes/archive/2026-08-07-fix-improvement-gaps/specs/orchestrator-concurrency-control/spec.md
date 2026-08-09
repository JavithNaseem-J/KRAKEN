## MODIFIED Requirements

### Requirement: Bounded worker pool and concurrency limit for agent graph
`services/orchestrator/main.py` SHALL execute `agent_graph.ainvoke` using an `asyncio.Semaphore` bounded concurrency control. The semaphore slot acquisition SHALL be non-blocking: the system SHALL check `semaphore.locked()` / acquire without a TOCTOU race. The semaphore size and worker count SHALL be configurable via environment variables (`ORCHESTRATOR_MAX_CONCURRENCY`, `ORCHESTRATOR_WORKERS`) with defaults of 5 and 4 respectively.

#### Scenario: Capacity available
- **WHEN** a `/run` request arrives and active graph executions are below the concurrency limit
- **THEN** the request acquires the semaphore slot and executes the async graph via `ainvoke`

#### Scenario: Concurrency limit reached
- **WHEN** a `/run` request arrives when all semaphore slots are in use
- **THEN** the server immediately returns HTTP 503 Service Unavailable with a busy message

#### Scenario: Concurrency limit is env-configurable
- **WHEN** `ORCHESTRATOR_MAX_CONCURRENCY=10` is set in the environment
- **THEN** the orchestrator allows up to 10 concurrent graph executions before returning 503

### Requirement: Approval callback resumptions use the bounded semaphore
The `POST /approval-callback` endpoint in `services/orchestrator/main.py` SHALL resume paused graphs through the same `graph_semaphore` used by `POST /run`. It SHALL NOT use `run_in_executor(None, ...)` (the unbounded default executor). Semaphore acquisition SHALL return HTTP 503 when no slot is available. The idempotency check (`SELECT FOR UPDATE`) SHALL occur first, but the resolution UPDATE SHALL occur after semaphore acquisition, so a capacity-related 503 leaves the approval in `pending` status and retryable by the caller.

#### Scenario: Callback resumes within capacity
- **WHEN** an approval callback arrives and a semaphore slot is available
- **THEN** the graph resumption executes via `ainvoke` and the semaphore slot is released when finished

#### Scenario: Callback rejected at concurrency limit
- **WHEN** an approval callback arrives while all semaphore slots are in use
- **THEN** the endpoint returns HTTP 503 Service Unavailable and the approval record remains in `pending` status (the resolution update was not committed)

#### Scenario: Callback never uses the default executor
- **WHEN** any graph resumption is triggered by `/approval-callback`
- **THEN** it runs via `ainvoke`, never on Python's unbounded default `ThreadPoolExecutor`

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

### Requirement: Memory writer uses non-blocking async execution
The `memory_writer_node` SHALL perform background message appending and long-term memory storing using non-blocking async HTTP tasks (`asyncio.create_task` with `app.state.http`). It SHALL NOT create a standalone module-level synchronous HTTP client or thread pool.

#### Scenario: Memory writing on graph completion
- **WHEN** the `memory_writer_node` executes at the end of a graph run
- **THEN** memory persistence tasks are scheduled asynchronously without spawning additional thread pools

### Requirement: CPU-bound model embedding offloaded to async thread
Calls to `BGEEmbedder.embed_query` and `embed_documents` in `services/knowledge/retriever.py` and `services/memory/long_term.py` SHALL be executed using `asyncio.to_thread(...)` (or `loop.run_in_executor`) to prevent blocking the main asyncio event loop during vector calculation.

#### Scenario: Retrieval under high request rate
- **WHEN** multiple concurrent requests call `retriever.retrieve(...)` or `memory.search(...)`
- **THEN** embedding calculation runs off-thread and does not stall concurrent event loop I/O

### Requirement: Episodic memory retrieval parses similarity score correctly
The `retriever_node` in `services/orchestrator/graph/nodes/retriever.py` SHALL parse the `similarity` field from episodic memory search responses (`ep.get("similarity", 0.8)`) rather than looking for a non-existent `score` field.

#### Scenario: Episodic memory returned with similarity score
- **WHEN** episodic memory search returns records with `"similarity": 0.94`
- **THEN** `retriever_node` assigns `relevance_score = 0.94` to the resulting chunk

## ADDED Requirements

### Requirement: Graceful shutdown drains concurrency semaphore
On process shutdown, the orchestrator SHALL set an internal drain flag to reject new `/run` requests with HTTP 503 and acquire `max_concurrency` semaphore slots to wait for active graph runs to complete.

#### Scenario: Orchestrator receives SIGTERM
- **WHEN** orchestrator process shuts down while graph executions are active
- **THEN** in-flight graph executions are allowed to finish releasing their semaphore slots before database connections and HTTP clients close

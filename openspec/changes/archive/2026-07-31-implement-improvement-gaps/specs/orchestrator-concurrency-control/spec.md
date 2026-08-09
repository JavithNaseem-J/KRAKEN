## ADDED Requirements

### Requirement: Bounded worker pool and concurrency limit for agent graph
`services/orchestrator/main.py` SHALL execute `agent_graph.invoke` using a bounded `ThreadPoolExecutor` and limit concurrent graph runs using an `asyncio.Semaphore`.

#### Scenario: Capacity available
- **WHEN** a `/run` request arrives and active graph executions are below the concurrency limit
- **THEN** the request acquires the semaphore and executes on the worker thread pool

#### Scenario: Concurrency limit reached
- **WHEN** a `/run` request arrives when all semaphore slots are in use
- **THEN** the server immediately returns HTTP 503 Service Unavailable with a busy message

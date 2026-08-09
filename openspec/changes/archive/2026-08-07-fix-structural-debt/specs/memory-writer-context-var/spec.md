## ADDED Requirements

### Requirement: Memory writer HTTP client context variable
The orchestrator service SHALL provide a module-level setting mechanism (`set_orchestrator_http_client(client)`) in `services/orchestrator/graph/nodes/memory_writer.py` or equivalent context variable layer, avoiding direct imports of `app` from `services.orchestrator.main`.

#### Scenario: Lifespan sets client context
- **WHEN** the orchestrator application starts up in lifespan
- **THEN** it calls `set_orchestrator_http_client(app.state.http)` to register the shared client

#### Scenario: Memory writer node uses context client
- **WHEN** `memory_writer_node` executes
- **THEN** it retrieves the client registered via context rather than importing `from services.orchestrator.main import app`

#### Scenario: Task exception logging callback
- **WHEN** `asyncio.create_task` is called in `memory_writer_node` or `approval/main.py`
- **THEN** a done callback (`add_done_callback`) is attached to log or surface any unhandled exceptions from the background task

## ADDED Requirements

### Requirement: Action handler dispatch offloaded to thread
The `POST /execute` endpoint in `services/action/main.py` SHALL execute synchronous `_dispatch()` calls using `asyncio.to_thread(_dispatch, ...)` to prevent blocking the FastAPI event loop during ticket mutation or database access.

#### Scenario: Concurrent action execution
- **WHEN** multiple action execution requests arrive concurrently
- **THEN** synchronous ticket handler calls execute off-thread, preserving event loop responsiveness for health checks and status endpoints

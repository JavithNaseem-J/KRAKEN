# action-dispatch Specification

## Purpose
Action execution dispatch and standardized exception handling.

## Requirements

### Requirement: Action handlers raise ActionExecutionError on execution failures
All handler functions in `services/action/handlers/ticket_handler.py` (`execute_auto_respond`, `execute_escalate`, `execute_request_info`, `execute_close`) SHALL raise `ActionExecutionError` directly when encountering invalid ticket IDs, missing payload attributes, or IO failures, rather than returning dictionary objects with `"status": "failure"`.

#### Scenario: Handler receives non-existent ticket ID
- **WHEN** `execute_escalate` is called with a ticket ID that does not exist in `data/knowledge/tickets/sample_tickets.json`
- **THEN** it raises `ActionExecutionError(f"Ticket '{ticket_id}' not found.")` directly to `services/action/main.py`

### Requirement: Action handler dispatch offloaded to thread
The `POST /execute` endpoint in `services/action/main.py` SHALL execute synchronous `_dispatch()` calls using `asyncio.to_thread(_dispatch, ...)` to prevent blocking the FastAPI event loop during ticket mutation or database access.

#### Scenario: Concurrent action execution
- **WHEN** multiple action execution requests arrive concurrently
- **THEN** synchronous ticket handler calls execute off-thread, preserving event loop responsiveness for health checks and status endpoints

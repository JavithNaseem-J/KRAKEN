# action-dispatch Specification

## Purpose
Delta spec for standardized error raising across action execution handlers.

## Requirements

### Requirement: Action handlers raise ActionExecutionError on execution failures
All handler functions in `services/action/handlers/ticket_handler.py` (`execute_auto_respond`, `execute_escalate`, `execute_request_info`, `execute_close`) SHALL raise `ActionExecutionError` directly when encountering invalid ticket IDs, missing payload attributes, or IO failures, rather than returning dictionary objects with `"status": "failure"`.

#### Scenario: Handler receives non-existent ticket ID
- **WHEN** `execute_escalate` is called with a ticket ID that does not exist in `data/knowledge/tickets/sample_tickets.json`
- **THEN** it raises `ActionExecutionError(f"Ticket '{ticket_id}' not found.")` directly to `services/action/main.py`

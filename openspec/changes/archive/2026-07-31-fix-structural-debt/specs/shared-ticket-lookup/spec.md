## ADDED Requirements

### Requirement: Ticket lookup helper
`services/action/handlers/ticket_handler.py` SHALL expose a module-level private function `_find_ticket(tickets: list[dict[str, Any]], ticket_id: str) -> dict[str, Any] | None`. It MUST perform a case-insensitive, whitespace-normalised match on the `id` field and return the matching ticket dict, or `None` if not found.

#### Scenario: Exact match found
- **WHEN** `_find_ticket(tickets, "TK-001")` is called and a ticket with `id == "TK-001"` exists
- **THEN** the matching ticket dict is returned

#### Scenario: Case-insensitive match
- **WHEN** `_find_ticket(tickets, "tk-001")` is called and a ticket with `id == "TK-001"` exists
- **THEN** the matching ticket dict is returned

#### Scenario: No match
- **WHEN** `_find_ticket(tickets, "TK-999")` is called and no such id exists
- **THEN** `None` is returned

### Requirement: Ticket handlers use shared lookup helper
All four ticket handler functions (`execute_auto_respond`, `execute_escalate`, `execute_request_info`, `execute_close`) SHALL use `_find_ticket()` instead of inline scan loops. Each function MUST raise `ActionExecutionError` when `_find_ticket()` returns `None`.

#### Scenario: Handler raises on missing ticket
- **WHEN** `execute_escalate("TK-999", ...)` is called and no ticket with that id exists
- **THEN** `ActionExecutionError` is raised with a message containing the ticket id

#### Scenario: Handler mutates returned ticket
- **WHEN** `execute_close("TK-001", ...)` is called and the ticket exists
- **THEN** the ticket's `status` is set to `"closed"` and the changes are saved via `_save_tickets()`

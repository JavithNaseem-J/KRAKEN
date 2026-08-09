# structural-debt-and-defect-fixes Specification

## Requirements

### Requirement: Robust Microservice Execution & Code Consistency
The system MUST execute action handlers, observability callbacks, and memory nodes cleanly without runtime NameErrors, duplicate retry logic, or unhandled async mismatches.

#### Scenario: Fallback File Ticket Creation
- **WHEN** PostgreSQL is unavailable and `execute_create_ticket()` falls back to file-based ticket storage
- **THEN** regex extraction executes cleanly with `import re` present, creating the ticket without raising a `NameError`.

#### Scenario: Langfuse Observability Setup
- **WHEN** Langfuse public and secret keys are configured in Settings
- **THEN** `get_langfuse_callback_handler()` instantiates `CallbackHandler` with both `public_key` and `secret_key` and configures the host cleanly.

#### Scenario: Dynamic Action Dispatching
- **WHEN** the action microservice receives an `ActionRequest`
- **THEN** `_dispatch()` resolves the handler function dynamically from a handler registry rather than evaluating manual `if/elif` branches.

#### Scenario: Asynchronous Memory Writer Node
- **WHEN** LangGraph executes the `memory_writer_node`
- **THEN** the node executes asynchronously (`async def`) using `app.state.http` without relying on module-global getter/setter state.

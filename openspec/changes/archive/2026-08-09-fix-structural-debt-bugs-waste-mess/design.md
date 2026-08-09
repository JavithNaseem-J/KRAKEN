## Context

An in-depth codebase audit identified 17 structural debt issues categorized across bugs, duplicate logic, over-engineering, dead code, and inconsistent patterns. This design outlines targeted refactorings to fix latent runtime errors, deduplicate logic, harmonize async interfaces, and clean unused code without changing external system APIs.

## Goals / Non-Goals

**Goals:**

- Fix latent runtime bugs (`import re` in `ticket_handler.py`, missing `secret_key` pass in `observability.py`, UUID `id` return type in `audit_store.py`).
- Centralize HTTP POST retry logic in `shared/http_client.py` and Ticket ID regular expressions in `shared/constants.py`.
- Convert `memory_writer_node` to `async def` for pattern consistency across LangGraph nodes, removing global `_http_client` getters/setters in favor of `app.state.http`.
- Replace hardcoded `if/elif` in `services/action/main.py` `_dispatch()` with a dynamic handler dictionary lookup registered alongside `shared/registry.py`.
- Consolidate redundant benchmark scripts into `scripts/benchmark.py` and prune dead imports/code.

**Non-Goals:**

- Adding new end-user capabilities or modifying external REST API endpoints/contracts.
- Rewriting core LangGraph state structures or checkpointer logic.

## Decisions

- **Decision 1: Shared HTTP Retry Decorator**: Create `post_with_retry(client, url, json_payload, headers)` helper in `shared/http_client.py` leveraging `tenacity` so HTTP client calls across orchestrator nodes share exponential backoff policies.
- **Decision 2: Single Source of Truth for Regex**: Create `shared/constants.py` defining `TICKET_ID_REGEX = re.compile(r"\b(?:TCK-\d+|TK-\d+)\b")` to prevent regex drift across microservices.
- **Decision 3: Handler Map in Action Service**: Define a `HANDLER_MAP: dict[str, Callable]` in `services/action/handlers/__init__.py` mapping action names directly to handler functions to eliminate manual `if/elif` routing in `services/action/main.py`.

## Risks / Trade-offs

- **Risk**: Modifying `memory_writer_node` from `def` to `async def` changes how LangGraph executes the node.
  - **Mitigation**: Ensure `build_graph_async` and all unit tests in `tests/unit/test_graph_nodes.py` are updated and pass with `async await`.

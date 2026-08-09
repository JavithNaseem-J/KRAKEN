## Why

The comprehensive senior AI/ML engineer audit identified 17 structural debt issues across the codebase (bugs, duplicate logic, over-engineering, dead code, and inconsistent patterns). Key high/medium severity bugs include a missing `import re` that causes runtime `NameError` during fallback ticket creation, missing `secret_key` pass-through in Langfuse initialization, duplicated HTTP retry logic, duplicated Ticket ID regex patterns, sync/async graph node inconsistencies, and hardcoded `if/elif` action dispatch logic. Resolving these issues improves system reliability, reduces maintenance overhead, and ensures code patterns are clean and consistent.

## What Changes

- **Bugs & Defect Fixes**:
  - Add missing `import re` in `services/action/handlers/ticket_handler.py`.
  - Pass `secret_key` and `host` to Langfuse `CallbackHandler` in `services/orchestrator/observability.py`.
  - Fix type annotations and return value casting in `services/audit/audit_store.py` (`audit_log.id` UUID vs `int`).
- **Logic & Structure Deduplication**:
  - Extract reusable HTTP retry decorator `post_with_retry` into `shared/http_client.py` and eliminate duplicate implementations in `services/orchestrator/graph/nodes/executor.py` and `retriever.py`.
  - Consolidate Ticket ID regex (`TICKET_ID_REGEX`) into `shared/constants.py` and reference it across knowledge and orchestrator retrievers.
  - Consolidate load testing scripts `scripts/benchmark.py` and `scripts/test_load_concurrency.py` into a single parameterized benchmark runner.
- **Over-Engineering & Pattern Harmonization**:
  - Refactor `services/action/main.py` `_dispatch()` to map action names dynamically using handler registries rather than hardcoded `if/elif` branches.
  - Convert `memory_writer_node` in `services/orchestrator/graph/nodes/memory_writer.py` to `async def` and replace process-global HTTP client getters/setters with `app.state.http`.
  - Extract inline stop-words set in `services/knowledge/retriever.py` to a module-level `frozenset` constant.
- **Dead Code Cleanup**:
  - Remove unused sync `build_graph()` function and dead `ConnectionPool` type imports in `services/orchestrator/graph/agent_graph.py`.
  - Move inline `import re` in orchestrator retriever node to top-level module imports.
  - Remove dead imports (`Distance, VectorParams`) in `services/knowledge/main.py`.

## Capabilities

### New Capabilities

- `structural-debt-and-defect-fixes`: Comprehensive structural debt cleanup across microservices including runtime bug fixes, retry logic deduplication, regex consolidation, and async node harmonization.

### Modified Capabilities

None.

## Impact

- `services/action/handlers/ticket_handler.py`: Added `import re`.
- `services/action/main.py`: Refactored handler dispatch mapping.
- `services/orchestrator/observability.py`: Fixed Langfuse callback handler instantiation.
- `services/orchestrator/graph/nodes/executor.py`: Replaced local retry function with `shared.http_client` utility.
- `services/orchestrator/graph/nodes/retriever.py`: Replaced local retry function and regex with `shared` utilities.
- `services/orchestrator/graph/nodes/memory_writer.py`: Converted node to `async def` and bound HTTP client to `app.state.http`.
- `services/orchestrator/graph/agent_graph.py`: Cleaned dead code and unused sync graph builder.
- `services/knowledge/retriever.py`: Used `shared.constants.TICKET_ID_REGEX` and module-level stop-words constant.
- `services/knowledge/main.py`: Removed dead imports.
- `services/audit/audit_store.py`: Fixed UUID return type handling.
- `shared/http_client.py`: Added `post_with_retry` helper.
- `shared/constants.py`: Added shared regex patterns and constants.
- `scripts/benchmark.py`: Enhanced to handle load concurrency scenarios, enabling deprecation of `test_load_concurrency.py`.

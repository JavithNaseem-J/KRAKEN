## Why

The comprehensive technical audit identified 9 key technical gaps, runtime bugs, and architectural flaws across the AKEA agent system:
1. Lack of multi-step reasoning and plan decomposition loops (Bonus requirement).
2. Absence of parallel action and tool execution capabilities (Bonus requirement).
3. Over-reliance on system prompts for knowledge grounding without code-enforced refusal guardrails when retrieved context is empty or low-relevance (Core requirement).
4. Memory duplication bug in short-term session memory where `memory_writer_node` duplicates previous turns on every run.
5. Async checkpointer runtime crash in `_reaper_loop` when calling synchronous `.invoke()` on an `AsyncPostgresSaver` compiled graph.
6. Vector DB empty state gap on fresh deployment where Qdrant collections are created empty without auto-ingestion.
7. Missing cryptographic audit log chain verification endpoint (`GET /verify-chain`) to detect database tampering.
8. Stale data risk in semantic response cache due to lack of TTL or invalidation on data mutation actions.
9. Responder formatting bug displaying `"Action 'None' was selected"` when decider node returns a null action.

Addressing these 9 issues ensures full compliance with the assessment brief, fixes active runtime memory and checkpointer crashes, and fortifies system safety, observability, and data integrity.

## What Changes

- Add multi-step plan decomposition and feedback loop routing in the Orchestrator's LangGraph DAG.
- Add support for parallel safe action dispatching using `asyncio.gather` in Decider and Executor nodes.
- Add a code-level relevance threshold check (0.40) and explicit refusal state in the Reasoner node when retrieved knowledge is absent or low-relevance.
- Fix session memory duplication in `memory_writer_node` by replacing full session history or appending only new turns.
- Fix `_reaper_loop` in Orchestrator main to use `await app.state.agent_graph.ainvoke(...)` for async checkpointer compatibility.
- Auto-trigger initial knowledge ingestion during `knowledge` service startup if Qdrant collection point count is 0.
- Add `GET /verify-chain` endpoint to `audit` service for SHA-256 cryptographic chain validation.
- Implement TTL and mutation invalidation for `SemanticCache`.
- Fix null action string handling in `responder_node`.

## Capabilities

### New Capabilities
- `multi-step-planning`: Enables the agent to break complex user queries into sub-goals, execute multi-step plans sequentially, and adjust steps based on intermediate tool results.
- `parallel-action-execution`: Enables the decider node to select multiple non-conflicting safe actions and execute them concurrently via async tasks.
- `grounding-guardrails`: Code-enforced threshold validation and refusal state when retrieved knowledge chunks are missing or fall below minimum relevance score.
- `session-memory-deduplication`: Corrects session memory persistence to prevent duplicate conversation turns in Redis.
- `reaper-async-fix`: Corrects background reaper loop graph resumption using `ainvoke` to support `AsyncPostgresSaver`.
- `knowledge-auto-ingest`: Auto-ingests knowledge files into Qdrant vector storage if collection is empty on startup.
- `audit-chain-verification`: Provides cryptographic verification of the append-only audit log SHA-256 hash chain.
- `semantic-cache-invalidation`: Implements TTL and mutation-based cache invalidation for vector response caching.
- `responder-null-action-safety`: Formats responder answers cleanly when no action or a null action is selected.

### Modified Capabilities

(None)

## Impact

- `services/orchestrator/graph/state.py`: Extended state schema for plan steps and action lists.
- `services/orchestrator/graph/agent_graph.py`: Conditional routing for multi-step execution loops.
- `services/orchestrator/graph/nodes/reasoner.py`: Code-level chunk relevance threshold and refusal handling.
- `services/orchestrator/graph/nodes/decider.py`: Multi-action selection support in Pydantic decision models.
- `services/orchestrator/graph/nodes/executor.py`: Parallel dispatching via `asyncio.gather` for safe actions.
- `services/orchestrator/graph/nodes/memory_writer.py`: Deduplicated message list passed to memory service.
- `services/orchestrator/graph/nodes/responder.py`: Robust null-action check and formatting.
- `services/orchestrator/main.py`: Updated reaper loop to await `ainvoke` for async checkpointer.
- `services/knowledge/main.py`: Added auto-ingestion logic in lifespan context.
- `services/audit/main.py` & `audit_store.py`: Added `/verify-chain` endpoint and verification method.
- `shared/cache.py`: Added TTL and invalidation hooks.
- `shared/models/agent.py`: API responses updated to include plan progress and multi-action results.

## 1. Grounding Guardrails & Refusal State

- [x] 1.1 Add relevance score filtering (threshold 0.40) and `insufficient_knowledge` flag in `services/orchestrator/graph/nodes/reasoner.py`
- [x] 1.2 Add explicit refusal prompt output when zero retrieved chunks satisfy the threshold score
- [x] 1.3 Add unit test in `tests/unit/test_graph_nodes.py` to verify low-relevance queries trigger refusal state without LLM hallucination


## 2. Parallel Action Execution

- [x] 2.1 Update `DecisionOutput` model in `services/orchestrator/graph/nodes/decider.py` and state schema in `services/orchestrator/graph/state.py` to support multi-action arrays
- [x] 2.2 Update `executor_node` in `services/orchestrator/graph/nodes/executor.py` to execute safe actions concurrently via `asyncio.gather`
- [x] 2.3 Add unit tests in `tests/unit/test_async_concurrency.py` verifying parallel safe action execution and error isolation


## 3. Multi-Step Planning Loop

- [x] 3.1 Extend `GraphState` in `services/orchestrator/graph/state.py` with `plan: list[str]` and `completed_steps: list[dict]`
- [x] 3.2 Add conditional edge routing `_route_after_execution` in `services/orchestrator/graph/agent_graph.py` to return to `reasoner` when sub-goals remain
- [x] 3.3 Add unit tests in `tests/unit/test_orchestrator.py` verifying multi-step graph loops and max step termination


## 4. Session Memory Deduplication & Async Reaper Fix

- [x] 4.1 Fix message payload extraction in `services/orchestrator/graph/nodes/memory_writer.py` to send only current turn messages to `/append`
- [x] 4.2 Fix background reaper loop in `services/orchestrator/main.py` to use `await app.state.agent_graph.ainvoke(...)` for `AsyncPostgresSaver` compatibility
- [x] 4.3 Add unit tests in `tests/unit/test_short_term_memory.py` and `tests/unit/test_orchestrator.py`


## 5. Startup Knowledge Auto-Ingestion & Audit Chain Verification

- [x] 5.1 Add collection point count check and `run_ingest_async` trigger in `services/knowledge/main.py` lifespan context
- [x] 5.2 Implement `verify_chain()` in `services/audit/audit_store.py` and expose `GET /verify-chain` endpoint in `services/audit/main.py`
- [x] 5.3 Add unit tests in `tests/unit/test_knowledge.py` and `tests/unit/test_audit.py`


## 6. Semantic Cache Invalidation & Responder Formatting Safety

- [x] 6.1 Add TTL validation and `invalidate()` method to `SemanticCache` in `shared/cache.py`
- [x] 6.2 Fix null action string formatting in `services/orchestrator/graph/nodes/responder.py`
- [x] 6.3 Add unit tests in `tests/unit/test_caching.py` and `tests/unit/test_graph_nodes.py`


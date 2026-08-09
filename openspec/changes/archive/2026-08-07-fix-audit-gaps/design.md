## Context

The comprehensive technical audit evaluated the AKEA system against core requirements, bonus goals, and production reliability bars. A total of 9 technical gaps, runtime bugs, and architectural flaws were identified:
1. Multi-step reasoning loops missing.
2. Parallel action/tool execution missing.
3. Code-enforced grounding refusal guardrails missing.
4. Session memory turn duplication in `memory_writer_node` & `short_term.py`.
5. `_reaper_loop` crash when invoking `AsyncPostgresSaver` synchronously.
6. Knowledge vector store unpopulated on fresh boot.
7. Audit SHA-256 hash chain verification endpoint missing.
8. Semantic response cache stale data risk without invalidation.
9. Responder node formatting bug when `selected_action` is `None`.

This design details the technical architecture to resolve all 9 items.

## Goals / Non-Goals

**Goals:**
- Implement multi-step planning loops in LangGraph (`executor` -> `reasoner` feedback loop when sub-goals remain).
- Enable parallel safe action execution in `decider_node` and `executor_node` using `asyncio.gather`.
- Implement a code-level relevance threshold (`0.40`) in `reasoner_node` to trigger a explicit refusal state when knowledge is missing/low-relevance.
- Fix session memory duplication by passing only newly generated turns or calling full-history update endpoints.
- Fix reaper loop async checkpointer invocation using `await ainvoke()`.
- Auto-ingest knowledge files on startup if Qdrant collection point count is 0.
- Implement `GET /verify-chain` endpoint in Audit service.
- Add TTL and mutation invalidation to `SemanticCache`.
- Handle `selected_action: None` gracefully in `responder_node`.

**Non-Goals:**
- Modifying the frontend-react UI components beyond supporting multi-action metadata.

## Decisions

### Decision 1: LangGraph Multi-Step Loop Routing
Extend `GraphState` with `plan: list[str]` and `completed_steps: list[dict]`. Add conditional edge `_route_after_execution` checking if `completed_steps < len(plan)`. If true and step count < MAX_STEPS (5), route back to `reasoner_node`.

### Decision 2: Concurrent Safe Action Execution with `asyncio.gather`
Update `DecisionOutput` model in `decider_node` to support `selected_actions: list[ActionDecision]`. `executor_node` separates safe vs. critical actions. Safe actions execute in parallel via `asyncio.gather(..., return_exceptions=True)`.

### Decision 3: Code-Level Chunk Relevance Filtering & Refusal State
In `reasoner_node`, filter out chunks with `relevance_score < 0.40`. If 0 valid chunks remain, set `insufficient_knowledge: True` and output an explicit refusal string.

### Decision 4: Session Memory Deduplication
In `memory_writer_node`, extract only newly added messages from this turn (e.g. `state["messages"][-1:]`) when calling `POST /session/{session_id}/append`, or replace the entire state via `POST /session/{session_id}`.

### Decision 5: Async Checkpointer Reaper Fix
In `_reaper_loop` (`services/orchestrator/main.py`), replace `run_in_executor(None, _resume_timeout)` with `await app.state.agent_graph.ainvoke(Command(resume={"decision": "timeout"}), config)`.

### Decision 6: Startup Knowledge Auto-Ingestion
In `services/knowledge/main.py` lifespan context, check `points_count`. If 0, execute `await run_ingest_async(app.state.client, app.state.embedder)` automatically.

### Decision 7: Audit Hash Chain Verification Endpoint
In `AuditStore`, add `verify_chain()` method that reads all rows in chronological order, recomputes `SHA-256(previous_hash:session_id:...:payload_str)`, and asserts equality with `entry_hash`. Expose via `GET /verify-chain`.

### Decision 8: Semantic Cache Invalidation & Expiry
In `SemanticCache`, attach a timestamp payload to entries and check max age (e.g. 1 hour). Expose an `invalidate()` method called by `action` service upon ticket mutation actions (`escalate`, `close`, `auto_respond`).

### Decision 9: Responder Null Action Handling
In `responder_node`, check `if selected_action is not None:` explicitly before forming string `Action '{selected_action}' was selected.`.

## Risks / Trade-offs

- **[Risk] Infinite Loops in Multi-Step Execution** → *Mitigation*: Hardcode `MAX_STEPS = 5` in `_route_after_execution`.
- **[Risk] Slow Startup during Auto-Ingestion** → *Mitigation*: Run auto-ingestion asynchronously only when point count is strictly 0.

## Migration Plan

1. Update data models in `shared/models/` and state in `services/orchestrator/graph/state.py`.
2. Implement relevance threshold filtering in `reasoner_node` and null check in `responder_node`.
3. Update `decider_node` and `executor_node` for parallel dispatch.
4. Update `agent_graph.py` and `main.py` for multi-step loops and async reaper execution.
5. Fix `memory_writer_node` turn deduplication.
6. Add auto-ingest in `knowledge/main.py` and `/verify-chain` in `audit/main.py`.
7. Add unit tests for all 9 capabilities.
